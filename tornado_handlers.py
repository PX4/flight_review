
import sys
import os
import tornado.web
# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.config import *
from plot_app.pyulog.ulog_parser import *
from multipart_streamer import MultiPartStreamer
from plot_app.helper import get_log_filename, validate_log_id
from send_email import send_notification_email
import uuid
from jinja2 import Environment, FileSystemLoader
import sqlite3
import datetime
import cgi # for html escaping


"""
Request handlers for Tornado web server
"""

UPLOAD_TEMPLATE = 'upload.html'

env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.realpath(__file__))))

class CustomHTTPError(tornado.web.HTTPError):
    def __init__(self, status_code, error_message=None):
        self.error_message = error_message
        super(CustomHTTPError, self).__init__(status_code, error_message)


@tornado.web.stream_request_body
class UploadHandler(tornado.web.RequestHandler):

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
                    'allowForAnalysis', 'obfuscated', 'source'])
                description = cgi.escape(form_data['description'].decode("utf-8"))
                email = form_data['email'].decode("utf-8")
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
                        'Source) values (?, ?, ?, ?, ?, ?, ?, ?)',
                        [log_id, title, description, upload_file_name,
                            datetime.datetime.now(), allow_for_analysis,
                            obfuscated, source])
                con.commit()
                cur.close()
                con.close()

                url = '/plot_app?log='+log_id

                send_notification_email(email, 'http://'+get_domain_name()+url,
                    description)

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

