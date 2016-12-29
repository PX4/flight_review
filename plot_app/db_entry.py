from helper import get_log_filename

from pyulog import *
from pyulog.px4 import *

import cgi # for html escaping


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

    def windSpeedStr(self):
        return self.windSpeedStrStatic(self.wind_speed)

    @staticmethod
    def windSpeedStrStatic(wind_speed):
        return {0: 'Calm', 5: 'Breeze', 8: 'Gale', 10: 'Storm'}.get(wind_speed, '')

    def ratingStr(self):
        return self.ratingStrStatic(self.rating)

    @staticmethod
    def ratingStrStatic(rating):
        return {'crash_pilot': 'Crashed (Pilot error)',
                'crash_sw_hw': 'Crashed (Software or Hardware issue)',
                'unsatisfactory': 'Unsatisfactory',
                'good': 'Good',
                'great': 'Great!'}.get(rating, '')


class DBDataGenerated:
    """ information from the generated DB entry """

    def __init__(self):
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


    @classmethod
    def fromLogFile(cls, log_id):
        """ initialize from a log file """
        obj = cls()

        ulog_file_name = get_log_filename(log_id)
        ulog = ULog(ulog_file_name)
        px4_ulog = PX4ULog(ulog)

        # extract information
        obj.duration_s = int((ulog.last_timestamp - ulog.start_timestamp)/1e6)
        obj.mav_type = px4_ulog.get_mav_type()
        obj.estimator = px4_ulog.get_estimator()
        obj.sys_autostart_id = ulog.initial_parameters.get('SYS_AUTOSTART', 0)
        obj.sys_hw = cgi.escape(ulog.msg_info_dict.get('ver_hw', ''))
        obj.ver_sw = cgi.escape(ulog.msg_info_dict.get('ver_sw', ''))
        version_info = ulog.get_version_info()
        if version_info is not None:
            obj.ver_sw_release = 'v{}.{}.{} {}'.format(*version_info)
        obj.num_logged_errors = 0
        obj.num_logged_warnings = 0

        for m in ulog.logged_messages:
            if m.log_level <= ord('3'):
                obj.num_logged_errors += 1
            if m.log_level == ord('4'):
                obj.num_logged_warnings += 1

        try:
            cur_dataset = [ elem for elem in ulog.data_list
                    if elem.name == 'commander_state' and elem.multi_id == 0][0]
            flight_mode_changes = cur_dataset.list_value_changes('main_state')
            obj.flight_modes = set([x[1] for x in flight_mode_changes])
        except (KeyError,IndexError) as error:
            obj.flight_modes = set()

        return obj

