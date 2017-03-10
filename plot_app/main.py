""" module that gets executed on a plotting page request """

from timeit import default_timer as timer
import sys
import sqlite3

from bokeh.io import curdoc
from bokeh.layouts import column, widgetbox
from bokeh.models.widgets import Div

from helper import *
from config import *
from colors import HTML_color_to_RGB
from db_entry import *
from configured_plots import generate_plots

#pylint: disable=invalid-name, redefined-outer-name, deprecated-method

start_time = timer()

ulog_file_name = 'test.ulg'

ulog_file_name = os.path.join(get_log_filepath(), ulog_file_name)
error_message = ''
log_id = ''

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

    ulog = load_ulog_file(ulog_file_name)
    px4_ulog = PX4ULog(ulog)
    px4_ulog.add_roll_pitch_yaw()
except:
    print("Error loading file:", sys.exc_info()[0], sys.exc_info()[1])
    error_message = 'An Error occured when trying to read the file.'


print_timing("Data Loading", start_time)
start_time = timer()


if error_message == '':

    # initialize flight mode changes
    try:
        cur_dataset = ulog.get_dataset('commander_state')
        flight_mode_changes = cur_dataset.list_value_changes('main_state')
        flight_mode_changes.append((ulog.last_timestamp, -1))
    except (KeyError, IndexError) as error:
        flight_mode_changes = []


    # read the data from DB
    db_data = DBData()
    vehicle_data = None
    try:
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Description, Feedback, Type, WindSpeed, Rating, VideoUrl '
                    'from Logs where Id = ?', [log_id])
        db_tuple = cur.fetchone()
        if db_tuple is not None:
            db_data.description = db_tuple[0]
            db_data.feedback = db_tuple[1]
            db_data.type = db_tuple[2]
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]

        # vehicle data
        if 'sys_uuid' in ulog.msg_info_dict:
            sys_uuid = cgi.escape(ulog.msg_info_dict['sys_uuid'])

            cur.execute('select LatestLogId, Name, FlightTime '
                        'from Vehicle where UUID = ?', [sys_uuid])
            db_tuple = cur.fetchone()
            if db_tuple is not None:
                vehicle_data = DBVehicleData()
                vehicle_data.log_id = db_tuple[0]
                if len(db_tuple[1]) > 0:
                    vehicle_data.name = db_tuple[1]
                try:
                    vehicle_data.flight_time = int(db_tuple[2])
                except:
                    pass

        cur.close()
        con.close()
    except:
        print("DB access failed:", sys.exc_info()[0], sys.exc_info()[1])


    # template variables
    curdoc().template_variables['google_maps_api_key'] = get_google_maps_api_key()
    curdoc().template_variables['is_plot_page'] = True
    curdoc().template_variables['log_id'] = log_id
    flight_modes = [
        {'name': 'Manual', 'color': HTML_color_to_RGB(flight_modes_table[0][1])},
        {'name': 'Altitude Control', 'color': HTML_color_to_RGB(flight_modes_table[1][1])},
        {'name': 'Position Control', 'color': HTML_color_to_RGB(flight_modes_table[2][1])},
        {'name': 'Acro', 'color': HTML_color_to_RGB(flight_modes_table[6][1])},
        {'name': 'Stabilized', 'color': HTML_color_to_RGB(flight_modes_table[8][1])},
        {'name': 'Offboard', 'color': HTML_color_to_RGB(flight_modes_table[7][1])},
        {'name': 'Rattitude', 'color': HTML_color_to_RGB(flight_modes_table[9][1])},
        {'name': 'Auto (Mission, RTL, Follow, ...)',
         'color': HTML_color_to_RGB(flight_modes_table[3][1])}
        ]
    curdoc().template_variables['flight_modes'] = flight_modes

    plots = generate_plots(ulog, px4_ulog, flight_mode_changes, db_data,
                           vehicle_data)

    title = 'Flight Review - '+px4_ulog.get_mav_type()


else:

    title = 'Error'

    div = Div(text="<h3>"+error_message+"</h3>", width=int(plot_width*0.9))
    plots = [widgetbox(div, width=int(plot_width*0.9))]


# layout
layout = column(plots, sizing_mode='scale_width')
curdoc().add_root(layout)
curdoc().title = title

print_timing("Plotting", start_time)
