"""
Request handlers for Tornado web server
"""

from __future__ import print_function
import sys
import os
import binascii
import uuid
import json
import shutil
import sqlite3
import datetime
import cgi # for html escaping
import tornado.web
from jinja2 import Environment, FileSystemLoader
from pyulog import *
from pyulog.ulog2kml import convert_ulog2kml
# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from config import *
from db_entry import *
from helper import get_log_filename, validate_log_id, \
    flight_modes_table, get_airframe_data, html_long_word_force_break, \
    validate_url, load_ulog_file, clear_ulog_cache, get_default_parameters, \
    get_total_flight_time, ULogException, get_airframe_name
from multipart_streamer import MultiPartStreamer
from send_email import send_notification_email, send_flightreport_email

#pylint: disable=maybe-no-member,attribute-defined-outside-init,abstract-method,too-many-statements
# TODO: cgi.escape got deprecated in python 3.2
#pylint: disable=deprecated-method


UPLOAD_TEMPLATE = 'upload.html'
BROWSE_TEMPLATE = 'browse.html'
EDIT_TEMPLATE = 'edit.html'

_ENV = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app/templates')))

class CustomHTTPError(tornado.web.HTTPError):
    """ simple class for HTTP exceptions with a custom error message """
    def __init__(self, status_code, error_message=None):
        self.error_message = error_message
        super(CustomHTTPError, self).__init__(status_code, error_message)


@tornado.web.stream_request_body
class UploadHandler(tornado.web.RequestHandler):
    """ Upload log file Tornado request handler: handles page requests and POST
    data """

    def initialize(self):
        self.multipart_streamer = None

    def prepare(self):
        if self.request.method.upper() == 'POST':
            if 'expected_size' in self.request.arguments:
                self.request.connection.set_max_body_size(
                    int(self.get_argument('expected_size')))
            try:
                total = int(self.request.headers.get("Content-Length", "0"))
            except KeyError:
                total = 0
            self.multipart_streamer = MultiPartStreamer(total)

    def data_received(self, chunk):
        if self.multipart_streamer:
            self.multipart_streamer.data_received(chunk)

    def get(self, *args, **kwargs):
        template = _ENV.get_template(UPLOAD_TEMPLATE)
        self.write(template.render())

    def post(self, *args, **kwargs):
        if self.multipart_streamer:
            try:
                self.multipart_streamer.data_complete()
                form_data = self.multipart_streamer.get_values(
                    ['description', 'email',
                     'allowForAnalysis', 'obfuscated', 'source', 'type',
                     'feedback', 'windSpeed', 'rating', 'videoUrl', 'public',
                     'vehicleName'])
                description = cgi.escape(form_data['description'].decode("utf-8"))
                email = form_data['email'].decode("utf-8")
                upload_type = 'personal'
                if 'type' in form_data:
                    upload_type = form_data['type'].decode("utf-8")
                source = 'webui'
                title = '' # may be used in future...
                if 'source' in form_data:
                    source = form_data['source'].decode("utf-8")
                obfuscated = 0
                if 'obfuscated' in form_data:
                    if form_data['obfuscated'].decode("utf-8") == 'true':
                        obfuscated = 1
                allow_for_analysis = 0
                if 'allowForAnalysis' in form_data:
                    if form_data['allowForAnalysis'].decode("utf-8") == 'true':
                        allow_for_analysis = 1
                feedback = ''
                if 'feedback' in form_data:
                    feedback = cgi.escape(form_data['feedback'].decode("utf-8"))
                wind_speed = -1
                rating = ''
                stored_email = ''
                video_url = ''
                is_public = 0
                vehicle_name = ''

                if upload_type == 'flightreport':
                    try:
                        wind_speed = int(cgi.escape(form_data['windSpeed'].decode("utf-8")))
                    except ValueError:
                        wind_speed = -1
                    rating = cgi.escape(form_data['rating'].decode("utf-8"))
                    if rating == 'notset': rating = ''
                    stored_email = email
                    # get video url & check if valid
                    video_url = cgi.escape(form_data['videoUrl'].decode("utf-8"), quote=True)
                    if not validate_url(video_url):
                        video_url = ''
                    if 'vehicleName' in form_data:
                        vehicle_name = cgi.escape(form_data['vehicleName'].decode("utf-8"))

                    # always allow for statistical analysis
                    allow_for_analysis = 1
                    if 'public' in form_data:
                        if form_data['public'].decode("utf-8") == 'true':
                            is_public = 1

                file_obj = self.multipart_streamer.get_parts_by_name('filearg')[0]
                upload_file_name = file_obj.get_filename()

                while True:
                    log_id = str(uuid.uuid4())
                    new_file_name = get_log_filename(log_id)
                    if not os.path.exists(new_file_name):
                        break

                # read file header & check if really an ULog file
                header_len = len(ULog.HEADER_BYTES)
                if (file_obj.get_payload_partial(header_len) !=
                        ULog.HEADER_BYTES):
                    if upload_file_name[-7:].lower() == '.px4log':
                        raise CustomHTTPError(
                            400,
                            'Invalid File. This seems to be a px4log file. '
                            'Upload it to <a href="http://logs.uaventure.com" '
                            'target="_blank">logs.uaventure.com</a>.')
                    raise CustomHTTPError(400, 'Invalid File')

                print('Moving uploaded file to', new_file_name)
                file_obj.move(new_file_name)

                if obfuscated == 1:
                    # TODO: randomize gps data, ...
                    pass

                # generate a token: secure random string (url-safe)
                token = str(binascii.hexlify(os.urandom(16)), 'ascii')

                # Load the ulog file but only if not uploaded via CI.
                # Then we open the DB connection.
                ulog = None
                if source != 'CI':
                    ulog_file_name = get_log_filename(log_id)
                    ulog = load_ulog_file(ulog_file_name)


                # put additional data into a DB
                con = sqlite3.connect(get_db_filename())
                cur = con.cursor()
                cur.execute(
                    'insert into Logs (Id, Title, Description, '
                    'OriginalFilename, Date, AllowForAnalysis, Obfuscated, '
                    'Source, Email, WindSpeed, Rating, Feedback, Type, '
                    'videoUrl, Public, Token) values '
                    '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [log_id, title, description, upload_file_name,
                     datetime.datetime.now(), allow_for_analysis,
                     obfuscated, source, stored_email, wind_speed, rating,
                     feedback, upload_type, video_url, is_public, token])

                if ulog is not None:
                    vehicle_data = update_vehicle_db_entry(cur, ulog, log_id, vehicle_name)
                    vehicle_name = vehicle_data.name

                con.commit()

                url = '/plot_app?log='+log_id
                full_plot_url = get_http_protocol()+'://'+get_domain_name()+url
                print(full_plot_url)

                delete_url = get_http_protocol()+'://'+get_domain_name()+ \
                    '/edit_entry?action=delete&log='+log_id+'&token='+token

                # information for the notification email
                info = {}
                info['description'] = description
                info['feedback'] = feedback
                info['upload_filename'] = upload_file_name
                info['type'] = ''
                info['airframe'] = ''
                info['hardware'] = ''
                info['uuid'] = ''
                info['software'] = ''
                if len(vehicle_name) > 0:
                    info['vehicle_name'] = vehicle_name

                if ulog is not None:
                    px4_ulog = PX4ULog(ulog)
                    info['type'] = px4_ulog.get_mav_type()
                    airframe_name_tuple = get_airframe_name(ulog)
                    if airframe_name_tuple is not None:
                        airframe_name, airframe_id = airframe_name_tuple
                        if len(airframe_name) == 0:
                            info['airframe'] = airframe_id
                        else:
                            info['airframe'] = airframe_name
                    sys_hardware = ''
                    if 'ver_hw' in ulog.msg_info_dict:
                        sys_hardware = cgi.escape(ulog.msg_info_dict['ver_hw'])
                        info['hardware'] = sys_hardware
                    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL':
                        info['uuid'] = cgi.escape(ulog.msg_info_dict['sys_uuid'])
                    branch_info = ''
                    if 'ver_sw_branch' in ulog.msg_info_dict:
                        branch_info = ' (branch: '+ulog.msg_info_dict['ver_sw_branch']+')'
                    if 'ver_sw' in ulog.msg_info_dict:
                        ver_sw = cgi.escape(ulog.msg_info_dict['ver_sw'])
                        info['software'] = ver_sw + branch_info


                if upload_type == 'flightreport' and is_public:
                    destinations = set(email_notifications_config['public_flightreport'])
                    if rating in ['unsatisfactory', 'crash_sw_hw', 'crash_pilot']:
                        destinations = destinations | \
                            set(email_notifications_config['public_flightreport_bad'])
                    send_flightreport_email(
                        list(destinations),
                        full_plot_url,
                        DBData.rating_str_static(rating),
                        DBData.wind_speed_str_static(wind_speed), delete_url,
                        stored_email, info)

                    # also generate the additional DB entry
                    # (we may have the log already loaded in 'ulog', however the
                    # lru cache will make it very quick to load it again)
                    generate_db_data_from_log_file(log_id, con)

                con.commit()
                cur.close()
                con.close()

                # send notification emails
                send_notification_email(email, full_plot_url, delete_url, info)

                # do not redirect for QGC
                if source != 'QGroundControl':
                    self.redirect(url)

            except CustomHTTPError:
                raise

            except ULogException:
                raise CustomHTTPError(
                    400,
                    'Failed to parse the file. It is most likely corrupt.')
            except:
                print('Error when handling POST data', sys.exc_info()[0],
                      sys.exc_info()[1])
                raise CustomHTTPError(500)

            finally:
                self.multipart_streamer.release_parts()

    def write_error(self, status_code, **kwargs):
        html_template = """
<html><title>Error {status_code}</title>
<body>HTTP Error {status_code}{error_message}</body>
</html>
"""
        error_message = ''
        if 'exc_info' in kwargs:
            e = kwargs["exc_info"][1]
            if isinstance(e, CustomHTTPError) and e.error_message:
                error_message = ': '+e.error_message
        self.write(html_template.format(status_code=status_code,
                                        error_message=error_message))


class DownloadHandler(tornado.web.RequestHandler):
    """ Download log file Tornado request handler """

    def get(self, *args, **kwargs):
        log_id = self.get_argument('log')
        if not validate_log_id(log_id):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')
        log_file_name = get_log_filename(log_id)
        download_type = self.get_argument('type', default='0')
        if not os.path.exists(log_file_name):
            raise tornado.web.HTTPError(404, 'Log not found')


        def get_original_filename(default_value, new_file_suffix):
            """
            get the uploaded file name & exchange the file extension
            """
            try:
                con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
                cur = con.cursor()
                cur.execute('select OriginalFilename '
                            'from Logs where Id = ?', [log_id])
                db_tuple = cur.fetchone()
                if db_tuple is not None:
                    original_file_name = cgi.escape(db_tuple[0])
                    if original_file_name[-4:].lower() == '.ulg':
                        original_file_name = original_file_name[:-4]
                    return original_file_name + new_file_suffix
                cur.close()
                con.close()
            except:
                print("DB access failed:", sys.exc_info()[0], sys.exc_info()[1])
            return default_value


        if download_type == '1': # download the parameters
            ulog = load_ulog_file(log_file_name)
            param_keys = sorted(ulog.initial_parameters.keys())

            self.set_header("Content-Type", "text/plain")
            self.set_header('Content-Disposition', 'inline; filename=params.txt')

            delimiter = ', '
            for param_key in param_keys:
                self.write(param_key)
                self.write(delimiter)
                self.write(str(ulog.initial_parameters[param_key]))
                self.write('\n')

        elif download_type == '2': # download the kml file
            kml_path = get_kml_filepath()
            kml_file_name = os.path.join(kml_path, log_id.replace('/', '.')+'.kml')

            # check if chached file exists
            if not os.path.exists(kml_file_name):
                print('need to create kml file', kml_file_name)

                def kml_colors(flight_mode):
                    """ flight mode colors for KML file """
                    if not flight_mode in flight_modes_table: flight_mode = 0

                    color_str = flight_modes_table[flight_mode][1][1:] # color in form 'ff00aa'

                    # increase brightness to match colors with template
                    rgb = [int(color_str[2*x:2*x+2], 16) for x in range(3)]
                    for i in range(3):
                        rgb[i] += 40
                        if rgb[i] > 255: rgb[i] = 255

                    color_str = "".join(map(lambda x: format(x, '02x'), rgb))

                    return 'ff'+color_str[4:6]+color_str[2:4]+color_str[0:2] # KML uses aabbggrr

                style = {'line_width': 2}
                # create in random temporary file, then move it (to avoid races)
                try:
                    temp_file_name = kml_file_name+'.'+str(uuid.uuid4())
                    convert_ulog2kml(log_file_name, temp_file_name,
                                     'vehicle_global_position', kml_colors,
                                     style=style,
                                     camera_trigger_topic_name='camera_capture')
                    shutil.move(temp_file_name, kml_file_name)
                except:
                    print('Error creating KML file', sys.exc_info()[0], sys.exc_info()[1])
                    raise CustomHTTPError(400, 'No Position Data in log')


            kml_dl_file_name = get_original_filename('track.kml', '.kml')

            # send the whole KML file
            self.set_header("Content-Type", "application/vnd.google-earth.kml+xml")
            self.set_header('Content-Disposition', 'attachment; filename='+kml_dl_file_name)
            with open(kml_file_name, 'rb') as kml_file:
                while True:
                    data = kml_file.read(4096)
                    if not data:
                        break
                    self.write(data)
                self.finish()

        elif download_type == '3': # download the non-default parameters
            ulog = load_ulog_file(log_file_name)
            param_keys = sorted(ulog.initial_parameters.keys())

            self.set_header("Content-Type", "text/plain")
            self.set_header('Content-Disposition', 'inline; filename=params.txt')

            default_params = get_default_parameters()

            delimiter = ', '
            for param_key in param_keys:
                try:
                    param_value = str(ulog.initial_parameters[param_key])
                    is_default = False

                    if param_key in default_params:
                        default_param = default_params[param_key]
                        if default_param['type'] == 'FLOAT':
                            is_default = abs(float(default_param['default']) -
                                             float(param_value)) < 0.00001
                        else:
                            is_default = int(default_param['default']) == int(param_value)

                    if not is_default:
                        self.write(param_key)
                        self.write(delimiter)
                        self.write(param_value)
                        self.write('\n')
                except:
                    pass

        else: # download the log file
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header("Content-Description", "File Transfer")
            self.set_header('Content-Disposition', 'attachment; filename={}'.format(
                os.path.basename(log_file_name)))
            with open(log_file_name, 'rb') as log_file:
                while True:
                    data = log_file.read(4096)
                    if not data:
                        break
                    self.write(data)
                self.finish()


    def write_error(self, status_code, **kwargs):
        html_template = """
<html><title>Error {status_code}</title>
<body>HTTP Error {status_code}{error_message}</body>
</html>
"""
        error_message = ''
        if 'exc_info' in kwargs:
            e = kwargs["exc_info"][1]
            if isinstance(e, CustomHTTPError) and e.error_message:
                error_message = ': '+e.error_message
        self.write(html_template.format(status_code=status_code,
                                        error_message=error_message))

def update_vehicle_db_entry(cur, ulog, log_id, vehicle_name):
    """
    Update the Vehicle DB entry
    :param cur: DB cursor
    :param ulog: ULog object
    :param vehicle_name: new vehicle name or '' if not updated
    :return vehicle_data: DBVehicleData object
    """

    vehicle_data = DBVehicleData()
    if 'sys_uuid' in ulog.msg_info_dict:
        vehicle_data.uuid = cgi.escape(ulog.msg_info_dict['sys_uuid'])

        if vehicle_name == '':
            cur.execute('select Name '
                        'from Vehicle where UUID = ?', [vehicle_data.uuid])
            db_tuple = cur.fetchone()
            if db_tuple is not None:
                vehicle_data.name = db_tuple[0]
            print('reading vehicle name from db:'+vehicle_data.name)
        else:
            vehicle_data.name = vehicle_name
            print('vehicle name from uploader:'+vehicle_data.name)

        vehicle_data.log_id = log_id
        flight_time = get_total_flight_time(ulog)
        if flight_time is not None:
            vehicle_data.flight_time = flight_time

        # update or insert the DB entry
        cur.execute('insert or replace into Vehicle (UUID, LatestLogId, Name, FlightTime)'
                    'values (?, ?, ?, ?)',
                    [vehicle_data.uuid, vehicle_data.log_id, vehicle_data.name,
                     vehicle_data.flight_time])
    return vehicle_data



def generate_db_data_from_log_file(log_id, db_connection=None):
    """
    Extract necessary information from the log file and insert as an entry to
    the LogsGenerated table (faster information retrieval later on).
    This is an expensive operation.
    It's ok to call this a second time for the same log, the call will just
    silently fail (but still read the whole log and will not update the DB entry)

    :return: DBDataGenerated object
    """

    db_data_gen = DBDataGenerated.from_log_file(log_id)

    need_closing = False
    if db_connection is None:
        db_connection = sqlite3.connect(get_db_filename())
        need_closing = True

    db_cursor = db_connection.cursor()
    try:
        db_cursor.execute(
            'insert into LogsGenerated (Id, Duration, '
            'Mavtype, Estimator, AutostartId, Hardware, '
            'Software, NumLoggedErrors, NumLoggedWarnings, '
            'FlightModes, SoftwareVersion, UUID, FlightModeDurations) values '
            '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [log_id, db_data_gen.duration_s, db_data_gen.mav_type,
             db_data_gen.estimator, db_data_gen.sys_autostart_id,
             db_data_gen.sys_hw, db_data_gen.ver_sw,
             db_data_gen.num_logged_errors,
             db_data_gen.num_logged_warnings,
             ','.join(map(str, db_data_gen.flight_modes)),
             db_data_gen.ver_sw_release, db_data_gen.vehicle_uuid,
             db_data_gen.flight_mode_durations_str()])
        db_connection.commit()
    except sqlite3.IntegrityError:
        # someone else already inserted it (race). just ignore it
        pass

    db_cursor.close()
    if need_closing:
        db_connection.close()

    return db_data_gen


class BrowseHandler(tornado.web.RequestHandler):
    """ Browse public log file Tornado request handler """

    def get(self, *args, **kwargs):
        table_header = """
        <thead>
            <tr>
                <th>#</th>
                <th>Upload Date</th>
                <th>Description</th>
                <th>Type</th>
                <th>Airframe</th>
                <th>Hardware</th>
                <th>Software</th>
                <th>Duration</th>
                <th>Rating</th>
                <th>Errors</th>
                <th>Flight Modes</th>
            </tr>
        </thead>
        <tbody>
        """
        table_footer = "</tbody>"
        table_data = ""

        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Id, Date, Description, WindSpeed, Rating, VideoUrl '
                    'from Logs where Public = 1')
        # need to fetch all here, because we will do more SQL calls while
        # iterating (having multiple cursor's does not seem to work)
        db_tuples = cur.fetchall()
        counter = 1
        for db_tuple in db_tuples:
            db_data = DBData()
            log_id = db_tuple[0]
            log_date = db_tuple[1].strftime('%Y-%m-%d')
            db_data.description = db_tuple[2]
            db_data.feedback = ''
            db_data.type = ''
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]

            # try to get the additional data from the DB
            cur.execute('select * from LogsGenerated where Id = ?', [log_id])
            db_tuple = cur.fetchone()
            if db_tuple is None: # need to generate from file
                try:
                    # Note that this is not necessary in most cases, as the entry is
                    # also generated after uploading (but with a timeout)
                    db_data_gen = generate_db_data_from_log_file(log_id, con)
                except Exception as e:
                    print('Failed to load log file: '+str(e))
                    continue
            else: # get it from the DB
                db_data_gen = DBDataGenerated()
                db_data_gen.duration_s = db_tuple[1]
                db_data_gen.mav_type = db_tuple[2]
                db_data_gen.estimator = db_tuple[3]
                db_data_gen.sys_autostart_id = db_tuple[4]
                db_data_gen.sys_hw = db_tuple[5]
                db_data_gen.ver_sw = db_tuple[6]
                db_data_gen.num_logged_errors = db_tuple[7]
                db_data_gen.num_logged_warnings = db_tuple[8]
                db_data_gen.flight_modes = \
                    set([int(x) for x in db_tuple[9].split(',') if len(x) > 0])
                db_data_gen.ver_sw_release = db_tuple[10]
                db_data_gen.vehicle_uuid = db_tuple[11]
                db_data_gen.flight_mode_durations = \
                    [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]

            # bring it into displayable form
            ver_sw = db_data_gen.ver_sw
            if len(ver_sw) > 10:
                ver_sw = ver_sw[:6]
            if len(db_data_gen.ver_sw_release) > 0:
                try:
                    release_split = db_data_gen.ver_sw_release.split()
                    release_type = int(release_split[1])
                    if release_type == 255: # it's a release
                        ver_sw = release_split[0]
                except:
                    pass
            airframe_data = get_airframe_data(db_data_gen.sys_autostart_id)
            if airframe_data is None:
                airframe = db_data_gen.sys_autostart_id
            else:
                airframe = airframe_data['name']

            flight_modes = ', '.join([flight_modes_table[x][0]
                                      for x in db_data_gen.flight_modes if x in
                                      flight_modes_table])

            m, s = divmod(db_data_gen.duration_s, 60)
            h, m = divmod(m, 60)
            duration_str = '{:d}:{:02d}:{:02d}'.format(h, m, s)

            # make sure to break long descriptions w/o spaces (otherwise they
            # mess up the layout)
            description = html_long_word_force_break(db_data.description)

            table_data += """
<tr>
<td>{counter}</td>
<td><a href="plot_app?log={log_id}">{date}</a></td>
<td>{description}</td>
<td>{mav_type}</td>
<td>{airframe}</td>
<td>{hw}</td>
<td>{sw}</td>
<td>{duration}</td>
<td>{rating}</td>
<td>{num_errors}</td>
<td>{flight_modes}</td>
</tr>
""".format(log_id=log_id, counter=counter,
           date=log_date,
           description=description,
           rating=db_data.rating_str(),
           wind_speed=db_data.wind_speed_str(),
           mav_type=db_data_gen.mav_type,
           airframe=airframe,
           hw=db_data_gen.sys_hw,
           sw=ver_sw,
           duration=duration_str,
           num_errors=db_data_gen.num_logged_errors,
           flight_modes=flight_modes
          )
            counter += 1

        cur.close()
        con.close()

        template = _ENV.get_template(BROWSE_TEMPLATE)
        self.write(template.render(table_data=table_header + table_data + table_footer))

class DBInfoHandler(tornado.web.RequestHandler):
    """ Get database info Tornado request handler """

    def get(self, *args, **kwargs):

        jsonlist = list()

        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Id, Date, Description, WindSpeed, Rating, VideoUrl '
                    'from Logs where Public = 1')
        # need to fetch all here, because we will do more SQL calls while
        # iterating (having multiple cursor's does not seem to work)
        db_tuples = cur.fetchall()
        counter = 1
        for db_tuple in db_tuples:
            jsondict = dict()
            db_data = DBData()
            log_id = db_tuple[0]
            jsondict['log_id'] = log_id
            jsondict['log_date'] = db_tuple[1].strftime('%Y-%m-%d')
            db_data.description = db_tuple[2]
            db_data.feedback = ''
            db_data.type = ''
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]
            jsondict.update(db_data.to_json_dict())

            # try to get the additional data from the DB
            cur.execute('select * from LogsGenerated where Id = ?', [log_id])
            db_tuple = cur.fetchone()
            if db_tuple is None: # need to generate from file
                try:
                    # Note that this is not necessary in most cases, as the entry is
                    # also generated after uploading (but with a timeout)
                    db_data_gen = generate_db_data_from_log_file(log_id, con)
                except Exception as e:
                    print('Failed to load log file: '+str(e))
                    continue
            else: # get it from the DB
                db_data_gen = DBDataGenerated()
                db_data_gen.duration_s = db_tuple[1]
                db_data_gen.mav_type = db_tuple[2]
                db_data_gen.estimator = db_tuple[3]
                db_data_gen.sys_autostart_id = db_tuple[4]
                db_data_gen.sys_hw = db_tuple[5]
                db_data_gen.ver_sw = db_tuple[6]
                db_data_gen.num_logged_errors = db_tuple[7]
                db_data_gen.num_logged_warnings = db_tuple[8]
                db_data_gen.flight_modes = \
                    set([int(x) for x in db_tuple[9].split(',') if len(x) > 0])
                db_data_gen.ver_sw_release = db_tuple[10]
                db_data_gen.vehicle_uuid = db_tuple[11]
                db_data_gen.flight_mode_durations = \
                    [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]

            jsondict.update(db_data_gen.to_json_dict())
            jsonlist.append(jsondict)

        cur.close()
        con.close()

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(jsonlist))

class EditEntryHandler(tornado.web.RequestHandler):
    """ Edit a log entry, with confirmation (currently only delete) """

    def get(self, *args, **kwargs):
        log_id = cgi.escape(self.get_argument('log'))
        action = self.get_argument('action')
        confirmed = self.get_argument('confirm', default='0')
        token = cgi.escape(self.get_argument('token'))

        if action == 'delete':
            if confirmed == '1':
                if self.delete_log_entry(log_id, token):
                    content = """
<h1>Log file deleted</h1>
<p>
Successfully deleted the log file.
</p>
"""
                else:
                    content = """
<h1>Failed</h1>
<p>
Failed to delete the log file.
</p>
"""
            else: # request user to confirm
                # use the same url, just append 'confirm=1'
                delete_url = self.request.path+'?action=delete&log='+log_id+ \
                        '&token='+token+'&confirm=1'
                content = """
<h1>Delete log file</h1>
<p>
Click <a href="{delete_url}">here</a> to confirm and delete the log {log_id}.
</p>
""".format(delete_url=delete_url, log_id=log_id)
        else:
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        template = _ENV.get_template(EDIT_TEMPLATE)
        self.write(template.render(content=content))


    @staticmethod
    def delete_log_entry(log_id, token):
        """
        delete a log entry (DB & file), validate token first

        :return: True on success
        """
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Token from Logs where Id = ?', (log_id,))
        db_tuple = cur.fetchone()
        if db_tuple is None:
            return False
        if token != db_tuple[0]: # validate token
            return False

        # kml file
        kml_path = get_kml_filepath()
        kml_file_name = os.path.join(kml_path, log_id.replace('/', '.')+'.kml')
        if os.path.exists(kml_file_name):
            os.unlink(kml_file_name)

        log_file_name = get_log_filename(log_id)
        print('deleting log entry {} and file {}'.format(log_id, log_file_name))
        os.unlink(log_file_name)
        cur.execute("DELETE FROM LogsGenerated WHERE Id = ?", (log_id,))
        cur.execute("DELETE FROM Logs WHERE Id = ?", (log_id,))
        con.commit()
        cur.close()
        con.close()

        # need to clear the cache as well
        clear_ulog_cache()

        return True
