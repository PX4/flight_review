"""
Tornado handler for the upload page
"""

from __future__ import print_function
import datetime
import os
from html import escape
import sys
import uuid
import binascii
import sqlite3
import tornado.web
from tornado.ioloop import IOLoop

from pyulog import ULog
from pyulog.px4 import PX4ULog

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from db_entry import DBVehicleData, DBData
from config import get_db_filename, get_http_protocol, get_domain_name, \
    email_notifications_config
from helper import get_total_flight_time, validate_url, get_log_filename, \
    load_ulog_file, get_airframe_name, ULogException
from overview_generator import generate_overview_img_from_id

#pylint: disable=relative-beyond-top-level
from .common import get_jinja_env, CustomHTTPError, generate_db_data_from_log_file, \
    TornadoRequestHandlerBase
from .send_email import send_notification_email, send_flightreport_email
from .multipart_streamer import MultiPartStreamer


UPLOAD_TEMPLATE = 'upload.html'


#pylint: disable=attribute-defined-outside-init,too-many-statements, unused-argument


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
        vehicle_data.uuid = escape(ulog.msg_info_dict['sys_uuid'])

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


@tornado.web.stream_request_body
class UploadHandler(TornadoRequestHandlerBase):
    """ Upload log file Tornado request handler: handles page requests and POST
    data """

    def initialize(self):
        """ initialize the instance """
        self.multipart_streamer = None

    def prepare(self):
        """ called before a new request """
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
        """ called whenever new data is received """
        if self.multipart_streamer:
            self.multipart_streamer.data_received(chunk)

    def get(self, *args, **kwargs):
        """ GET request callback """
        template = get_jinja_env().get_template(UPLOAD_TEMPLATE)
        self.write(template.render())

    def post(self, *args, **kwargs):
        """ POST request callback """
        if self.multipart_streamer:
            try:
                self.multipart_streamer.data_complete()
                form_data = self.multipart_streamer.get_values(
                    ['description', 'email',
                     'allowForAnalysis', 'obfuscated', 'source', 'type',
                     'feedback', 'windSpeed', 'rating', 'videoUrl', 'public',
                     'vehicleName'])
                description = escape(form_data['description'].decode("utf-8"))
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
                    feedback = escape(form_data['feedback'].decode("utf-8"))
                wind_speed = -1
                rating = ''
                stored_email = ''
                video_url = ''
                is_public = 0
                vehicle_name = ''
                error_labels = ''

                if upload_type == 'flightreport':
                    try:
                        wind_speed = int(escape(form_data['windSpeed'].decode("utf-8")))
                    except ValueError:
                        wind_speed = -1
                    rating = escape(form_data['rating'].decode("utf-8"))
                    if rating == 'notset': rating = ''
                    stored_email = email
                    # get video url & check if valid
                    video_url = escape(form_data['videoUrl'].decode("utf-8"), quote=True)
                    if not validate_url(video_url):
                        video_url = ''
                    if 'vehicleName' in form_data:
                        vehicle_name = escape(form_data['vehicleName'].decode("utf-8"))

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
                    'videoUrl, ErrorLabels, Public, Token) values '
                    '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [log_id, title, description, upload_file_name,
                     datetime.datetime.now(), allow_for_analysis,
                     obfuscated, source, stored_email, wind_speed, rating,
                     feedback, upload_type, video_url, error_labels, is_public, token])

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
                info['rating'] = rating
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
                        sys_hardware = escape(ulog.msg_info_dict['ver_hw'])
                        info['hardware'] = sys_hardware
                    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL':
                        info['uuid'] = escape(ulog.msg_info_dict['sys_uuid'])
                    branch_info = ''
                    if 'ver_sw_branch' in ulog.msg_info_dict:
                        branch_info = ' (branch: '+ulog.msg_info_dict['ver_sw_branch']+')'
                    if 'ver_sw' in ulog.msg_info_dict:
                        ver_sw = escape(ulog.msg_info_dict['ver_sw'])
                        info['software'] = ver_sw + branch_info


                if upload_type == 'flightreport' and is_public and source != 'CI':
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
                    # also generate the preview image
                    IOLoop.instance().add_callback(generate_overview_img_from_id, log_id)

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

            except ULogException as e:
                raise CustomHTTPError(
                    400,
                    'Failed to parse the file. It is most likely corrupt.') from e
            except Exception as e:
                print('Error when handling POST data', sys.exc_info()[0],
                      sys.exc_info()[1])
                raise CustomHTTPError(500) from e

            finally:
                self.multipart_streamer.release_parts()

