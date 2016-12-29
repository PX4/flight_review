
from timeit import default_timer as timer
import time
import re
import os
import numpy as np
from config import get_log_filepath, get_airframes_filename, get_airframes_url
from urllib.request import urlretrieve
import xml.etree.ElementTree # airframe parsing
import shutil
import uuid

__DO_PRINT_TIMING = False

def print_timing(name, start_time):
    global __DO_PRINT_TIMING
    if __DO_PRINT_TIMING:
        print(name + " took: {:.3} s".format(timer() - start_time))


# the following is for using the plotting app locally
__LOG_ID_IS_FILENAME_TEST_FILE = '/tmp/.plotting_app_log_id_is_filename'
def set_log_id_is_filename(enable=False):
    """ treat the log_id as filename instead of id if enable=True.

    WARNING: this disables log id validation, so that all log id's are valid.
    Don't use it on a live server! """

    # this is ugly but there seems to be no better way to pass some variable
    # from the serve.py script to the plotting application
    if enable:
        with open(__LOG_ID_IS_FILENAME_TEST_FILE, 'w') as f:
            f.write('enable')
    else:
        if os.path.exists(__LOG_ID_IS_FILENAME_TEST_FILE):
            os.unlink(__LOG_ID_IS_FILENAME_TEST_FILE)

def _check_log_id_is_filename():
    return os.path.exists(__LOG_ID_IS_FILENAME_TEST_FILE)



def validate_log_id(log_id):
    """ Check whether the log_id has a valid form (not whether it actually
    exists) """
    if _check_log_id_is_filename():
        return True
    # we are a bit less restrictive than the actual format
    if re.match(r'^[0-9a-zA-Z_-]+$', log_id):
        return True
    return False

def get_log_filename(log_id):
    """ return the ulog file name from a log id in the form:
        xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    """
    if _check_log_id_is_filename():
        return log_id
    return os.path.join(get_log_filepath(), log_id + '.ulg')


def download_airframes_maybe():
    """ download the airframes.xml if it does not exist or it's older than a day.
        returns True if the file can be used
    """
    airframes_file = get_airframes_filename()
    need_download = False
    if os.path.exists(airframes_file):
        elapsed_sec = time.time() - os.path.getmtime(airframes_file)
        if elapsed_sec / 3600 > 24:
            need_download = True
            os.unlink(airframes_file)
    else:
        need_download = True
    if need_download:
        print("Downloading airframes from "+get_airframes_url())
        try:
            # download to a temporary random file, then move to avoid race
            # conditions
            temp_file_name = airframes_file+'.'+str(uuid.uuid4())
            urlretrieve(get_airframes_url(), temp_file_name)
            shutil.move(temp_file_name, airframes_file)
        except Exception as e:
            print("Download error: "+str(e))
            return False
    return True

def get_airframe_data(airframe_id):
    """ return a dict of aiframe data ('name' & 'type') from an autostart id.
    Downloads aiframes if necessary. Returns None on error
    """

    if download_airframes_maybe():
        try:
            airframe_xml = get_airframes_filename()
            e = xml.etree.ElementTree.parse(airframe_xml).getroot()
            for airframe_group in e.findall('airframe_group'):
                for airframe in airframe_group.findall('airframe'):
                    if str(airframe_id) == airframe.get('id'):
                        ret = {'name': airframe.get('name')}
                        try:
                            ret['type'] = airframe.find('type').text
                        except:
                            pass
                        return ret
        except:
            pass
    return None

flight_modes_table = {
    0: ('Manual', '#cc0000'), # red
    1: ('Altitude', '#222222'), # gray
    2: ('Position', '#00cc33'), # green
    6: ('Acro', '#66cc00'), # olive
    8: ('Stabilized', '#0033cc'), # dark blue
    7: ('Offboard', '#00cccc'), # light blue
    9: ('Rattitude', '#cc9900'), # orange

    3: ('Mission', '#6600cc'), # purple
    4: ('Loiter', '#6600cc'), # purple
    5: ('Return to Land', '#6600cc'), # purple
    10: ('Takeoff', '#6600cc'), # purple
    11: ('Land', '#6600cc'), # purple
    12: ('Follow Target', '#6600cc'), # purple
    }


def WGS84_to_mercator(lon, lat):
    """ Convert lon, lat in [deg] to Mercator projection """
# alternative that relies on the pyproj library:
# import pyproj # GPS coordinate transformations
#    wgs84 = pyproj.Proj('+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs')
#    mercator = pyproj.Proj('+proj=merc +a=6378137 +b=6378137 +lat_ts=0.0 +lon_0=0.0 +x_0=0.0 +y_0=0 +units=m +k=1.0 +nadgrids=@null +no_defs')
#    return pyproj.transform(wgs84, mercator, lon, lat)

    semimajorAxis = 6378137.0  # WGS84 spheriod semimajor axis
    east = lon * 0.017453292519943295
    north = lat * 0.017453292519943295
    northing = 3189068.5 * np.log((1.0 + np.sin(north)) / (1.0 - np.sin(north)))
    easting = semimajorAxis * east

    return easting, northing

def map_projection(lat, lon, anchor_lat, anchor_lon):
    """ convert lat, lon in [rad] to x, y in [m] with an anchor position """
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    cos_d_lon = np.cos(lon - anchor_lon)
    sin_anchor_lat = np.sin(anchor_lat)
    cos_anchor_lat = np.cos(anchor_lat)

    arg = sin_anchor_lat * sin_lat + cos_anchor_lat * cos_lat * cos_d_lon;
    arg[arg > 1] = 1
    arg[arg < -1] = -1

    np.set_printoptions(threshold=np.nan)
    c = np.arccos(arg)
    k = np.copy(lat)
    for i in range(len(lat)):
        if np.abs(c[i]) < np.finfo(float).eps:
            k[i] = 1
        else:
            k[i] = c[i] / np.sin(c[i])

    CONSTANTS_RADIUS_OF_EARTH = 6371000
    x = k * (cos_anchor_lat * sin_lat - sin_anchor_lat * cos_lat * cos_d_lon) * CONSTANTS_RADIUS_OF_EARTH
    y = k * cos_lat * np.sin(lon - anchor_lon) * CONSTANTS_RADIUS_OF_EARTH

    return x, y


def html_long_word_force_break(text, max_length = 15):
    """
    force line breaks for text that contains long words, suitable for HTML
    display
    """
    ret = ''
    for d in text.split(' '):
        while len(d) > max_length:
            ret += d[:max_length]+'<wbr />'
            d = d[max_length:]
        ret += d+' '

    if len(ret) > 0:
        return ret[:-1]
    return ret

def validate_url(url):
    """
    check if valid url provided

    :return: True if valid, False otherwise
    """
    # source: http://stackoverflow.com/questions/7160737/python-how-to-validate-a-url-in-python-malformed-or-not
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return regex.match(url) is not None
