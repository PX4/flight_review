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
        return {0: 'Calm', 5: 'Breeze', 8: 'Gale', 10: 'Storm'}.get(self.wind_speed, '')

    def ratingStr(self):
        return {'crash_pilot': 'Crashed (Pilot mistake)',
                'crash_sw_hw': 'Crashed (Software or Hardware issue)',
                'unsatisfactory': 'Unsatisfactory',
                'good': 'Good',
                'great': 'Great!'}.get(self.rating, '')


class DBDataGenerated:
    """ information from the generated DB entry """

    def __init__(self, log_id):
        """ initialize from a log file """

        ulog_file_name = get_log_filename(log_id)
        ulog = ULog(ulog_file_name)
        px4_ulog = PX4ULog(ulog)

        # extract information
        self.duration_s = int((ulog.last_timestamp - ulog.start_timestamp)/1e6)
        self.mav_type = px4_ulog.get_mav_type()
        self.estimator = px4_ulog.get_estimator()
        self.sys_autostart_id = ulog.initial_parameters.get('SYS_AUTOSTART', 0)
        self.sys_hw = cgi.escape(ulog.msg_info_dict.get('ver_hw', ''))
        self.ver_sw = cgi.escape(ulog.msg_info_dict.get('ver_sw', ''))
        self.num_logged_errors = 0
        self.num_logged_warnings = 0

        for m in ulog.logged_messages:
            if m.log_level <= ord('3'):
                self.num_logged_errors += 1
            if m.log_level == ord('4'):
                self.num_logged_warnings += 1

        try:
            cur_dataset = [ elem for elem in ulog.data_list
                    if elem.name == 'commander_state' and elem.multi_id == 0][0]
            flight_mode_changes = cur_dataset.list_value_changes('main_state')
            self.flight_modes = set([x[1] for x in flight_mode_changes])
        except (KeyError,IndexError) as error:
            self.flight_modes = set()

