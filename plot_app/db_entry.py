""" Database entry classes """

from html import escape

from pyulog import *
from pyulog.px4 import *

from helper import get_log_filename, load_ulog_file

#pylint: disable=missing-docstring, too-few-public-methods

class DBData:
    """ simple class that contains information from the DB entry of a single
    log file """
    def __init__(self):
        self.description = ''
        self.feedback = ''
        self.type = 'personal'
        self.wind_speed = -1
        self.rating = ''
        self.video_url = ''
        self.error_labels = []
        self.source = ''

        super().__init__()

    def wind_speed_str(self):
        return self.wind_speed_str_static(self.wind_speed)

    @staticmethod
    def wind_speed_str_static(wind_speed):
        return {0: 'Calm', 5: 'Breeze', 8: 'Gale', 10: 'Storm'}.get(wind_speed, '')

    def rating_str(self):
        return self.rating_str_static(self.rating)

    @staticmethod
    def rating_str_static(rating):
        return {'crash_pilot': 'Crashed (Pilot error)',
                'crash_sw_hw': 'Crashed (Software or Hardware issue)',
                'unsatisfactory': 'Unsatisfactory',
                'good': 'Good',
                'great': 'Great!'}.get(rating, '')

    def to_json_dict(self):
        jsondict = dict()
        jsondict['description'] = self.description
        jsondict['feedback'] = self.feedback
        jsondict['type'] = self.type
        jsondict['wind_speed'] = self.wind_speed
        jsondict['rating'] = self.rating
        jsondict['video_url'] = self.video_url
        jsondict['error_labels'] = self.error_labels
        jsondict['source'] = self.source
        return jsondict


class DBDataGenerated:
    """ information from the generated DB entry """

    def __init__(self):
        self.start_time_utc = 0
        self.duration_s = 0
        self.mav_type = ''
        self.estimator = ''
        self.sys_autostart_id = 0
        self.sys_hw = ''
        self.ver_sw = ''
        self.ver_sw_release = ''
        self.num_logged_errors = 0
        self.num_logged_warnings = 0
        self.flight_modes = set()
        self.vehicle_uuid = ''
        self.flight_mode_durations = [] # list of tuples of (mode, duration sec)
        super().__init__()

    def flight_mode_durations_str(self):
        ret = []
        for duration in self.flight_mode_durations:
            ret.append(str(duration[0])+':'+str(duration[1]))
        return ','.join(ret)

    @classmethod
    def from_log_file(cls, log_id):
        """ initialize from a log file """
        obj = cls()

        ulog_file_name = get_log_filename(log_id)
        ulog = load_ulog_file(ulog_file_name)
        px4_ulog = PX4ULog(ulog)

        # extract information
        obj.duration_s = int((ulog.last_timestamp - ulog.start_timestamp)/1e6)
        obj.mav_type = px4_ulog.get_mav_type()
        obj.estimator = px4_ulog.get_estimator()
        obj.sys_autostart_id = ulog.initial_parameters.get('SYS_AUTOSTART', 0)
        obj.sys_hw = escape(ulog.msg_info_dict.get('ver_hw', ''))
        obj.ver_sw = escape(ulog.msg_info_dict.get('ver_sw', ''))
        version_info = ulog.get_version_info()
        if version_info is not None:
            obj.ver_sw_release = 'v{}.{}.{} {}'.format(*version_info)
        obj.num_logged_errors = 0
        obj.num_logged_warnings = 0
        if 'sys_uuid' in ulog.msg_info_dict:
            obj.vehicle_uuid = escape(ulog.msg_info_dict['sys_uuid'])

        for m in ulog.logged_messages:
            if m.log_level <= ord('3'):
                obj.num_logged_errors += 1
            if m.log_level == ord('4'):
                obj.num_logged_warnings += 1

        try:
            cur_dataset = ulog.get_dataset('vehicle_status')
            flight_mode_changes = cur_dataset.list_value_changes('nav_state')
            obj.flight_modes = {int(x[1]) for x in flight_mode_changes}

            # get the durations
            # make sure the first entry matches the start of the logging
            if len(flight_mode_changes) > 0:
                flight_mode_changes[0] = (ulog.start_timestamp, flight_mode_changes[0][1])
            flight_mode_changes.append((ulog.last_timestamp, -1))
            for i in range(len(flight_mode_changes)-1):
                flight_mode = int(flight_mode_changes[i][1])
                flight_mode_duration = int((flight_mode_changes[i+1][0] -
                                            flight_mode_changes[i][0]) / 1e6)
                obj.flight_mode_durations.append((flight_mode, flight_mode_duration))

        except (KeyError, IndexError) as error:
            obj.flight_modes = set()

        # logging start time & date
        try:
           # get the first non-zero timestamp
            gps_data = ulog.get_dataset('vehicle_gps_position')
            indices = np.nonzero(gps_data.data['time_utc_usec'])
            if len(indices[0]) > 0:
                obj.start_time_utc = int(gps_data.data['time_utc_usec'][indices[0][0]] / 1000000)
        except:
            # Ignore. Eg. if topic not found
            pass


        return obj

    def to_json_dict(self):
        jsondict = dict()
        jsondict['duration_s'] = int(self.duration_s)
        jsondict['mav_type'] = self.mav_type
        jsondict['estimator'] = self.estimator
        jsondict['sys_autostart_id'] = int(self.sys_autostart_id)
        jsondict['sys_hw'] = self.sys_hw
        jsondict['ver_sw'] = self.ver_sw
        jsondict['ver_sw_release'] = self.ver_sw_release
        jsondict['num_logged_errors'] = self.num_logged_errors
        jsondict['num_logged_warnings'] = self.num_logged_warnings
        jsondict['flight_modes'] = list(self.flight_modes)
        jsondict['vehicle_uuid'] = self.vehicle_uuid
        jsondict['flight_mode_durations'] = self.flight_mode_durations
        return jsondict

class DBVehicleData:
    """ simple class that contains information from the DB entry of a vehicle """
    def __init__(self):
        self.uuid = None
        self.log_id = ''
        self.name = ''
        self.flight_time = 0

