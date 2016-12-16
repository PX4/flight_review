
import sys
import os
import tornado.web
# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.config import *
from plot_app.db_entry import *
from pyulog import *
from pyulog.ulog2kml import convert_ulog2kml
from multipart_streamer import MultiPartStreamer
from plot_app.helper import get_log_filename, validate_log_id, \
    flight_modes_table, get_airframe_data
from send_email import send_notification_email, send_flightreport_email
import uuid
from jinja2 import Environment, FileSystemLoader
import shutil
import sqlite3
import datetime
import cgi # for html escaping


"""
Request handlers for Tornado web server
"""

UPLOAD_TEMPLATE = 'upload.html'
BROWSE_TEMPLATE = 'browse.html'

env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.realpath(__file__))))

class CustomHTTPError(tornado.web.HTTPError):
    def __init__(self, status_code, error_message=None):
        self.error_message = error_message
        super(CustomHTTPError, self).__init__(status_code, error_message)


@tornado.web.stream_request_body
class UploadHandler(tornado.web.RequestHandler):
    """ Upload log file Tornado request handler: handles page requests and POST
    data """

    def initialize(self):
        self.ps = None

    def prepare(self):
        if self.request.method.upper() == 'POST':
            if 'expected_size' in self.request.arguments:
                self.request.connection.set_max_body_size(
                        int(self.get_argument('expected_size')))
            try:
                total = int(self.request.headers.get("Content-Length", "0"))
            except KeyError:
                total = 0
            self.ps = MultiPartStreamer(total)

    def data_received(self, data):
        if self.ps:
            self.ps.data_received(data)

    def get(self):
        template = env.get_template(UPLOAD_TEMPLATE)
        self.write(template.render())

    def post(self):
        if self.ps:
            try:
                self.ps.data_complete()
                form_data = self.ps.get_values(['description', 'email',
                    'allowForAnalysis', 'obfuscated', 'source', 'type',
                    'feedback', 'windSpeed', 'rating', 'videoUrl', 'public'])
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

                if upload_type == 'flightreport':
                    try:
                        wind_speed = int(cgi.escape(form_data['windSpeed'].decode("utf-8")))
                    except ValueError:
                        wind_speed = -1
                    rating = cgi.escape(form_data['rating'].decode("utf-8"))
                    if rating == 'notset': rating = ''
                    stored_email = email
                    video_url = cgi.escape(form_data['videoUrl'].decode("utf-8"), quote=True)
                    # always allow for statistical analysis
                    allow_for_analysis = 1
                    if 'public' in form_data:
                        if form_data['public'].decode("utf-8") == 'true':
                            is_public = 1

                file_obj = self.ps.get_parts_by_name('filearg')[0]
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
                        raise CustomHTTPError(400,
                            'Invalid File. This seems to be a px4log file. '
                            'Upload it to <a href="http://logs.uaventure.com" '
                            'target="_blank">logs.uaventure.com</a>.')
                    raise CustomHTTPError(400, 'Invalid File')

                print('Moving uploaded file to', new_file_name)
                file_obj.move(new_file_name)

                if obfuscated == 1:
                    # TODO: randomize gps data, ...
                    pass

                # put additional data into a DB
                con = sqlite3.connect(get_db_filename())
                cur = con.cursor()
                cur.execute('insert into Logs (Id, Title, Description, '
                        'OriginalFilename, Date, AllowForAnalysis, Obfuscated, '
                        'Source, Email, WindSpeed, Rating, Feedback, Type, '
                        'videoUrl, Public) values '
                        '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        [log_id, title, description, upload_file_name,
                            datetime.datetime.now(), allow_for_analysis,
                            obfuscated, source, stored_email, wind_speed, rating,
                            feedback, upload_type, video_url, is_public])
                con.commit()
                cur.close()
                con.close()

                url = '/plot_app?log='+log_id
                full_plot_url = 'http://'+get_domain_name()+url

                # send notification emails
                send_notification_email(email, full_plot_url, description)

                if upload_type == 'flightreport' and is_public:
                    send_flightreport_email(email_notifications_config['public_flightreport'],
                            full_plot_url, description, feedback,
                            DBData.ratingStrStatic(rating),
                            DBData.windSpeedStrStatic(wind_speed))

                # do not redirect for QGC
                if not source == 'QGroundControl':
                    self.redirect(url)

            except CustomHTTPError:
                raise

            except:
                print('Error when handling POST data', sys.exc_info()[0],
                        sys.exc_info()[1])
                raise CustomHTTPError(500)

            finally:
                self.ps.release_parts()

    def write_error(self, status_code, **kwargs):
        html_template="""
<html><title>Error {status_code}</title>
<body>HTTP Error {status_code}{error_message}</body>
</html>
"""
        error_message=''
        if 'exc_info' in kwargs:
            e = kwargs["exc_info"][1]
            if isinstance(e, CustomHTTPError) and e.error_message:
                error_message=': '+e.error_message
        self.write(html_template.format(status_code=status_code,
            error_message=error_message))


class DownloadHandler(tornado.web.RequestHandler):
    """ Download log file Tornado request handler """

    def get(self):
        log_id = self.get_argument('log')
        if not validate_log_id(log_id):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')
        log_file_name = get_log_filename(log_id)
        download_type = self.get_argument('type', default='0')
        if not os.path.exists(log_file_name):
            raise tornado.web.HTTPError(404, 'Log not found')

        if download_type == '1': # download the parameters
            ulog = ULog(log_file_name, [])
            param_keys = sorted(ulog.initial_parameters.keys())

            self.set_header("Content-Type", "text/plain")
            self.set_header('Content-Disposition', 'inline; filename=params.txt')

            delimiter = ', '
            for param_key in param_keys:
                self.write(param_key)
                self.write(delimiter)
                self.write(str(ulog.initial_parameters[param_key]))
                self.write('\n')

        if download_type == '2': # download the kml file
            kml_path = get_kml_filepath()
            kml_file_name = os.path.join(kml_path, log_id.replace('/', '.')+'.kml')

            # check if chached file exists
            if not os.path.exists(kml_file_name):
                print('need to create kml file', kml_file_name)

                def kml_colors(x):
                    """ flight mode colors for KML file """
                    if not x in flight_modes_table: x = 0

                    color_str = flight_modes_table[x][1][1:] # color in form 'ff00aa'

                    # increase brightness to match colors with template
                    rgb = [int(color_str[2*x:2*x+2], 16) for x in range(3)]
                    for i in range(3):
                        rgb[i] += 40
                        if rgb[i] > 255: rgb[i] = 255

                    color_str = "".join(map(lambda x: format(x, '02x'),rgb))

                    return 'ff'+color_str[4:6]+color_str[2:4]+color_str[0:2] # KML uses aabbggrr

                style = {'line_width': 2}
                # create in random temporary file, then move it (to avoid races)
                temp_file_name = kml_file_name+'.'+str(uuid.uuid4())
                convert_ulog2kml(log_file_name, temp_file_name, 'vehicle_global_position',
                    kml_colors, style=style)
                shutil.move(temp_file_name, kml_file_name)


            # send the whole KML file
            self.set_header("Content-Type", "text/plain")
            self.set_header('Content-Disposition', 'attachment; filename=track.kml')
            with open(kml_file_name, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    self.write(data)
                self.finish()

        else: # download the log file
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header("Content-Description", "File Transfer")
            self.set_header('Content-Disposition', 'attachment; filename={}'.format(
                os.path.basename(log_file_name)))
            with open(log_file_name, 'rb') as f:
                while True:
                    data = f.read(4096)
                    if not data:
                        break
                    self.write(data)
                self.finish()


class BrowseHandler(tornado.web.RequestHandler):
    """ Browse public log file Tornado request handler """

    def get(self):
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
            if db_tuple == None: # need to generate from file
                db_data_gen = DBDataGenerated.fromLogFile(log_id)

                try:
                    cur.execute('insert into LogsGenerated (Id, Duration, '
                            'Mavtype, Estimator, AutostartId, Hardware, '
                            'Software, NumLoggedErrors, NumLoggedWarnings, '
                            'FlightModes) values '
                            '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            [log_id, db_data_gen.duration_s, db_data_gen.mav_type,
                            db_data_gen.estimator, db_data_gen.sys_autostart_id,
                            db_data_gen.sys_hw, db_data_gen.ver_sw,
                            db_data_gen.num_logged_errors,
                            db_data_gen.num_logged_warnings,
                            ','.join(map(str, db_data_gen.flight_modes)) ])
                    con.commit()
                except sqlite3.IntegrityError:
                    # someone else already inserted it (race). just ignore it
                    pass
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
                db_data_gen.flight_modes = set([int(x)
                    for x in db_tuple[9].split(',') if len(x) > 0])

            # bring it into displayable form
            ver_sw = db_data_gen.ver_sw
            if len(ver_sw) > 10:
                ver_sw = ver_sw[:6]
            airframe_data = get_airframe_data(db_data_gen.sys_autostart_id)
            if airframe_data == None:
                airframe = db_data_gen.sys_autostart_id
            else:
                airframe = airframe_data['name']

            flight_modes = ', '.join([ flight_modes_table[x][0]
                    for x in db_data_gen.flight_modes if x in
                    flight_modes_table])

            m, s = divmod(db_data_gen.duration_s, 60)
            h, m = divmod(m, 60)
            duration_str = '{:d}:{:02d}:{:02d}'.format(h, m, s)

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
                    description=db_data.description,
                    rating=db_data.ratingStr(),
                    wind_speed=db_data.windSpeedStr(),
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

        template = env.get_template(BROWSE_TEMPLATE)
        self.write(template.render(table_data = table_header + table_data +
            table_footer))

