""" configuration variables """

import configparser
import os


#pylint: disable=bad-whitespace, invalid-name

# load the config
_conf = configparser.ConfigParser()
_cur_dir = os.path.dirname(os.path.realpath(__file__))
_conf.read_file(open(os.path.join(_cur_dir, '../config_default.ini')))
_user_config_file = os.path.join(_cur_dir, '../config_user.ini')
if os.path.exists(_user_config_file):
    _conf.read_file(open(_user_config_file))

email_config = dict(_conf.items('email'))

email_notifications_config = dict(_conf.items('email_notifications'))
email_notifications_config['public_flightreport'] = \
    [ s.strip() for s in email_notifications_config['public_flightreport'].split(',')]
email_notifications_config['public_flightreport_bad'] = \
    [ s.strip() for s in email_notifications_config['public_flightreport_bad'].split(',')]

__DOMAIN_NAME = _conf.get('general', 'domain_name')
__HTTP_PROTOCOL = _conf.get('general', 'http_protocol')
__AIRFRAMES_URL = _conf.get('general', 'airframes_url')
__PARAMETERS_URL = _conf.get('general', 'parameters_url')
__MAPBOX_API_ACCESS_TOKEN = _conf.get('general', 'mapbox_api_access_token')
__BING_API_KEY = _conf.get('general', 'bing_maps_api_key')
__CESIUM_API_KEY = _conf.get('general', 'cesium_api_key')
__LOG_CACHE_SIZE = int(_conf.get('general', 'log_cache_size'))
__DB_FILENAME_CUSTOM = _conf.get('general', 'db_filename')

__STORAGE_PATH = _conf.get('general', 'storage_path')
if not os.path.isabs(__STORAGE_PATH):
    __STORAGE_PATH = os.path.join(_cur_dir, '..', __STORAGE_PATH)

__LOG_FILE_PATH = os.path.join(__STORAGE_PATH, 'log_files')
__DB_FILENAME = os.path.join(__STORAGE_PATH, 'logs.sqlite')
__CACHE_FILE_PATH = os.path.join(__STORAGE_PATH, 'cache')
__AIRFRAMES_FILENAME = os.path.join(__CACHE_FILE_PATH, 'airframes.xml')
__PARAMETERS_FILENAME = os.path.join(__CACHE_FILE_PATH, 'parameters.xml')
__RELEASES_FILENAME = os.path.join(__CACHE_FILE_PATH, 'releases.json')

__PRINT_TIMING = int(_conf.get('debug', 'print_timing'))
__VERBOSE_OUTPUT = int(_conf.get('debug', 'verbose_output'))

# general configuration variables for plotting
plot_width = 840

plot_color_blue = '#2877a2' # or: #3539e0

plot_config = dict(
    maps_line_color = plot_color_blue,
    plot_width = plot_width,
    plot_height = dict(
        normal = int(plot_width / 2.1),
        small = int(plot_width / 2.5),
        large = int(plot_width / 1.61803398874989484), # used for the gps map
        ),
    )

colors3 = ['#e0212d', '#208900', plot_color_blue]
colors2 = [colors3[0], colors3[1]] # for data to express: 'what it is' and 'what it should be'
colors8 = [colors3[0], colors3[1], colors3[2], '#333333', '#999999', '#e58C33',
           '#33e5e5', '#e533e5']
color_gray = '#464646'

plot_config['mission_setpoint_color'] = colors8[5]


def get_domain_name():
    """ get configured domain name (w/o http://) """
    return __DOMAIN_NAME

def get_http_protocol():
    """ get the protocol: either http or https """
    return __HTTP_PROTOCOL

def get_log_filepath():
    """ get configured log files directory """
    return __LOG_FILE_PATH

def get_cache_filepath():
    """ get configured cache directory """
    return __CACHE_FILE_PATH

def get_kml_filepath():
    """ get configured KML files directory """
    return os.path.join(get_cache_filepath(), 'kml')

def get_overview_img_filepath():
    """ get configured overview image directory """
    return os.path.join(get_cache_filepath(), 'img')

def get_db_filename():
    """ get configured DB file name """
    if __DB_FILENAME_CUSTOM != "":
        return __DB_FILENAME_CUSTOM
    return __DB_FILENAME

def get_airframes_filename():
    """ get configured airframes file name """
    return __AIRFRAMES_FILENAME

def get_airframes_url():
    """ get airframes download URL """
    return __AIRFRAMES_URL

def get_releases_filename():
    """ get configured releases file name """
    return __RELEASES_FILENAME

def get_parameters_filename():
    """ get configured parameters file name """
    return __PARAMETERS_FILENAME

def get_parameters_url():
    """ get parameters download URL """
    return __PARAMETERS_URL

def get_mapbox_api_access_token():
    """ get MapBox API Access Token """
    return __MAPBOX_API_ACCESS_TOKEN

def get_bing_maps_api_key():
    """ get Bing maps API key """
    return __BING_API_KEY

def get_cesium_api_key():
    """ get Cesium API key """
    return __CESIUM_API_KEY

def get_log_cache_size():
    """ get maximum number of cached logs in RAM """
    return __LOG_CACHE_SIZE

def debug_print_timing():
    """ print timing information? """
    return __PRINT_TIMING == 1

def debug_verbose_output():
    """ print verbose output? """
    return __VERBOSE_OUTPUT == 1
