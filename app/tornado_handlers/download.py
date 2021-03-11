"""
Tornado handler for the download page
"""

from __future__ import print_function
import os
from html import escape
import sys
import uuid
import shutil
import sqlite3
import tornado.web

from pyulog.ulog2kml import convert_ulog2kml

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from helper import get_log_filename, validate_log_id, \
    flight_modes_table, load_ulog_file, get_default_parameters

from config import get_db_filename, get_kml_filepath

#pylint: disable=relative-beyond-top-level
from .common import CustomHTTPError, TornadoRequestHandlerBase

#pylint: disable=abstract-method, unused-argument

class DownloadHandler(TornadoRequestHandlerBase):
    """ Download log file Tornado request handler """

    def get(self, *args, **kwargs):
        """ GET request callback """
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
                    original_file_name = escape(db_tuple[0])
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
                except Exception as e:
                    print('Error creating KML file', sys.exc_info()[0], sys.exc_info()[1])
                    raise CustomHTTPError(400, 'No Position Data in log') from e


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

