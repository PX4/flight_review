
from colors import get_N_colors
import os


email_config = dict(
    SMTPserver = "smtp.my_email_domain.net", # This will use SSL, with port 465
    sender     = "me@my_email_domain.net",

    user_name  = "USER_NAME_FOR_INTERNET_SERVICE_PROVIDER",
    password   = "PASSWORD_INTERNET_SERVICE_PROVIDER",
    )

__DOMAIN_NAME = "localhost:5006" # web site url = eg. 'http://' + __DOMAIN_NAME + '/upload'


__STORAGE_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), '../data')

__LOG_FILE_PATH = os.path.join(__STORAGE_PATH, 'log_files')
__DB_FILENAME = os.path.join(__STORAGE_PATH, 'logs.sqlite')
__CACHE_FILE_PATH = os.path.join(__STORAGE_PATH, 'cache')
__AIRFRAMES_FILENAME = os.path.join(__CACHE_FILE_PATH, 'airframes.xml')

__AIRFRAMES_URL = "http://px4-travis.s3.amazonaws.com/Firmware/master/airframes.xml"

# https://developers.google.com/maps/documentation/javascript/get-api-key
__GMAPS_API_KEY = ""


# notification emails to send on uploading new logs
email_notifications_config = dict(
    public_flightreport = [] # list of email addresses
    )

# general configuration variables for plotting
plot_width = 840

plot_color_blue = '#2877a2' # or: #3539e0

plot_config = dict(
        maps_line_color = plot_color_blue,
        plot_width = plot_width,
        plot_height = dict(
            normal = int(plot_width / 2.1),
            small = int(plot_width / 2.5),
            gps_map = int(plot_width / 1.61803398874989484),
            ),
        )

colors3 = ['#e0212d', '#208900', plot_color_blue]
colors2 = [colors3[0], colors3[1]] # for data to express: 'what it is' and 'what it should be'
colors8 = get_N_colors(8, 0.7)

plot_config['mission_setpoint_color'] = colors8[4]


def get_domain_name():
    return __DOMAIN_NAME

def get_log_filepath():
    return __LOG_FILE_PATH

def get_cache_filepath():
    return __CACHE_FILE_PATH

def get_kml_filepath():
    return os.path.join(get_cache_filepath(), 'kml')

def get_db_filename():
    return __DB_FILENAME

def get_airframes_filename():
    return __AIRFRAMES_FILENAME

def get_airframes_url():
    return __AIRFRAMES_URL

def get_google_maps_api_key():
    return __GMAPS_API_KEY
