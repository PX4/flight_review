from bokeh.io import curdoc
from bokeh.layouts import row, column, widgetbox
from bokeh.models.widgets import Div

import numpy as np
from timeit import default_timer as timer
import sys
import sqlite3

from pyulog import *
from pyulog.px4 import *

from helper import *
from config import *
from configured_plots import generate_plots



start_time = timer()


def load_data(file_name):
    # load only the messages we really need
    msg_filter = ['battery_status', 'distance_sensor', 'estimator_status',
            'sensor_combined', 'cpuload', 'commander_state',
            'vehicle_gps_position', 'vehicle_local_position',
            'vehicle_local_position_setpoint',
            'vehicle_global_position', 'actuator_controls', 'actuator_controls_0',
            'actuator_controls_1', 'actuator_outputs',
            'vehicle_attitude', 'vehicle_attitude_setpoint',
            'vehicle_rates_setpoint', 'rc_channels', 'input_rc',
            'position_setpoint_triplet' ]
    ulog = ULog(file_name, msg_filter)
    px4_ulog = PX4ULog(ulog)
    px4_ulog.add_roll_pitch_yaw()

    # filter messages with timestamp = 0 (these are invalid).
    # The better way is not to publish such messages in the first place, and fix
    # the code instead (it goes against the monotonicity requirement of ulog).
    # So we display the values such that the problem becomes visible.
#    for d in ulog.data_list:
#        t = d.data['timestamp']
#        non_zero_indices = t != 0
#        if not np.all(non_zero_indices):
#            d.data = np.compress(non_zero_indices, d.data, axis=0)

    data = ulog.data_list
    return ulog, px4_ulog


ulog_file_name = 'test.ulg'

ulog_file_name = os.path.join(get_log_filepath(), ulog_file_name)
error_message = ''

try:
    GET_arguments = curdoc().session_context.request.arguments

    if GET_arguments is not None and 'log' in GET_arguments:
        log_args = GET_arguments['log']
        if len(log_args) == 1:
            log_id = str(log_args[0], 'utf-8')
            if not validate_log_id(log_id):
                raise ValueError('Invalid log id: {}'.format(log_id))
            print('GET[log]={}'.format(log_id))
            ulog_file_name = get_log_filename(log_id)

    ulog, px4_ulog = load_data(ulog_file_name)
except:
    print("Error loading file:", sys.exc_info()[0], sys.exc_info()[1])
    error_message = 'An Error occured when trying to read the file.'


print_timing("Data Loading", start_time)
start_time = timer()


if error_message == '':

    # initialize flight mode changes
    try:
        cur_dataset = [ elem for elem in ulog.data_list
                if elem.name == 'commander_state' and elem.multi_id == 0][0]
        flight_mode_changes = cur_dataset.list_value_changes('main_state')
        flight_mode_changes.append((ulog.last_timestamp, -1))
    except (KeyError,IndexError) as error:
        flight_mode_changes = []


    # read the description from DB
    log_description = ''
    try:
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Description from Logs where Id = ?', [log_id])
        db_tuple = cur.fetchone()
        if db_tuple != None:
            log_description = db_tuple[0]
        cur.close()
        con.close()
    except:
        print("DB access failed:", sys.exc_info()[0], sys.exc_info()[1])


    plots = generate_plots(ulog, px4_ulog, flight_mode_changes, log_description)

    title = 'Flight Review - '+px4_ulog.get_mav_type()

else:

    title = 'Error'

    div = Div(text="<h3>"+error_message+"</h3>", width=int(plot_width*0.9))
    plots = [ widgetbox(div, width = int(plot_width*0.9)) ]


# layout
layout = column(plots, sizing_mode='scale_width')
curdoc().add_root(layout)
curdoc().title = title

print_timing("Plotting", start_time)
