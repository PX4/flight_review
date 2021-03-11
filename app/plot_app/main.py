""" module that gets executed on a plotting page request """

from timeit import default_timer as timer
import sys
import sqlite3
import traceback
import os

from html import escape

from bokeh.io import curdoc
from bokeh.layouts import column
from bokeh.models.widgets import Div

from helper import *
from config import *
from colors import HTML_color_to_RGB
from db_entry import *
from configured_plots import generate_plots
from pid_analysis_plots import get_pid_analysis_plots
from statistics_plots import StatisticsPlots

#pylint: disable=invalid-name, redefined-outer-name


GET_arguments = curdoc().session_context.request.arguments
if GET_arguments is not None and 'stats' in GET_arguments:

    # show the statistics page

    plots = []
    start_time = timer()
    statistics = StatisticsPlots(plot_config, debug_verbose_output())

    print_timing("Data Loading Stats", start_time)
    start_time = timer()


    # title
    div = Div(text="<h3>Statistics</h3>")
    plots.append(column(div))

    div = Div(text="<h4>All Logs</h4>")
    plots.append(column(div))

    p = statistics.plot_log_upload_statistics([colors8[0], colors8[1], colors8[3],
                                               colors8[4], colors8[5]])
    plots.append(p)
    div_info = Div(text="Number of Continous Integration (Simulation Tests) Logs: %i<br />" \
            "Total Number of Logs on the Server: %i" %
                   (statistics.num_logs_ci(), statistics.num_logs_total()))
    plots.append(column(div_info))

    div = Div(text="<br/><h4>Flight Report Logs "
              "<small class='text-muted'>(Public Logs only)</small></h4>")
    div_info = Div(text="Total Flight Hours over all versions: %.1f"%
                   statistics.total_public_flight_duration())
    div_info_release = Div(text="Total Flight Hours for the latest major" \
            " release %s (starting from the first RC candidate): %.1f"%
                           (statistics.latest_major_release()+'.x',
                            statistics.total_public_flight_duration_latest_release()))
    plots.append(column([div, div_info, div_info_release]))

    p = statistics.plot_public_airframe_statistics()
    plots.append(p)

    p = statistics.plot_public_boards_statistics()
    plots.append(p)

    p = statistics.plot_public_boards_num_flights_statistics()
    plots.append(p)

    p = statistics.plot_public_flight_mode_statistics()
    plots.append(p)

    # TODO: add a rating pie chart (something like
    # http://bokeh.pydata.org/en/latest/docs/gallery/donut_chart.html ?)

    print_timing("Plotting Stats", start_time)

    curdoc().template_variables['is_stats_page'] = True

    layout = column(plots, sizing_mode='scale_width')
    curdoc().add_root(layout)
    curdoc().title = "Flight Review - Statistics"


else:
    # show the plots of a single log

    start_time = timer()

    ulog_file_name = 'test.ulg'

    ulog_file_name = os.path.join(get_log_filepath(), ulog_file_name)
    error_message = ''
    log_id = ''

    try:

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

    except ULogException:
        error_message = ('A parsing error occured when trying to read the file - '
                         'the log is most likely corrupt.')
    except:
        print("Error loading file:", sys.exc_info()[0], sys.exc_info()[1])
        error_message = 'An error occured when trying to read the file.'


    print_timing("Data Loading", start_time)
    start_time = timer()

    if error_message == '':

        # read the data from DB
        db_data = DBData()
        vehicle_data = None
        try:
            con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
            cur = con.cursor()
            cur.execute('select Description, Feedback, Type, WindSpeed, Rating, VideoUrl, '
                        'ErrorLabels from Logs where Id = ?', [log_id])
            db_tuple = cur.fetchone()
            if db_tuple is not None:
                db_data.description = db_tuple[0]
                db_data.feedback = db_tuple[1]
                db_data.type = db_tuple[2]
                db_data.wind_speed = db_tuple[3]
                db_data.rating = db_tuple[4]
                db_data.video_url = db_tuple[5]
                db_data.error_labels = sorted(
                    [int(x) for x in db_tuple[6].split(',') if len(x) > 0]) \
                    if db_tuple[6] else []

            # vehicle data
            if 'sys_uuid' in ulog.msg_info_dict:
                sys_uuid = escape(ulog.msg_info_dict['sys_uuid'])

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

        def show_exception_page():
            """ show an error page in case of an unknown/unhandled exception """
            title = 'Internal Error'

            error_message = ('<h3>Internal Server Error</h3>'
                             '<p>Please open an issue on <a '
                             'href="https://github.com/PX4/flight_review/issues" target="_blank">'
                             'https://github.com/PX4/flight_review/issues</a> with a link '
                             'to this log.')
            div = Div(text=error_message, width=int(plot_width*0.9))
            plots = [column(div, width=int(plot_width*0.9))]
            curdoc().template_variables['internal_error'] = True
            return (title, error_message, plots)


        # check which plots to show
        plots_page = 'default'
        if GET_arguments is not None and 'plots' in GET_arguments:
            plots_args = GET_arguments['plots']
            if len(plots_args) == 1:
                plots_page = str(plots_args[0], 'utf-8')
        if plots_page == 'pid_analysis':
            try:
                link_to_main_plots = '?log='+log_id
                plots = get_pid_analysis_plots(ulog, px4_ulog, db_data,
                                               link_to_main_plots)

                title = 'Flight Review - '+px4_ulog.get_mav_type()

            except Exception as error:
                # catch all errors to avoid showing a blank page. Note that if we
                # get here, there's a bug somewhere that needs to be fixed!
                traceback.print_exc()
                title, error_message, plots = show_exception_page()

        else:
            # template variables
            curdoc().template_variables['cur_err_ids'] = db_data.error_labels
            curdoc().template_variables['mapbox_api_access_token'] = get_mapbox_api_access_token()
            curdoc().template_variables['is_plot_page'] = True
            curdoc().template_variables['log_id'] = log_id
            flight_modes = [
                {'name': 'Manual', 'color': HTML_color_to_RGB(flight_modes_table[0][1])},
                {'name': 'Altitude Control', 'color': HTML_color_to_RGB(flight_modes_table[1][1])},
                {'name': 'Position Control', 'color': HTML_color_to_RGB(flight_modes_table[2][1])},
                {'name': 'Acro', 'color': HTML_color_to_RGB(flight_modes_table[10][1])},
                {'name': 'Stabilized', 'color': HTML_color_to_RGB(flight_modes_table[15][1])},
                {'name': 'Offboard', 'color': HTML_color_to_RGB(flight_modes_table[14][1])},
                {'name': 'Rattitude', 'color': HTML_color_to_RGB(flight_modes_table[16][1])},
                {'name': 'Auto (Mission, RTL, Follow, ...)',
                 'color': HTML_color_to_RGB(flight_modes_table[3][1])}
                ]
            curdoc().template_variables['flight_modes'] = flight_modes
            vtol_modes = [
                {'name': 'Transition', 'color': HTML_color_to_RGB(vtol_modes_table[1][1])},
                {'name': 'Fixed-Wing', 'color': HTML_color_to_RGB(vtol_modes_table[2][1])},
                {'name': 'Multicopter', 'color': HTML_color_to_RGB(vtol_modes_table[3][1])},
                ]
            curdoc().template_variables['vtol_modes'] = vtol_modes

            link_to_3d_page = '3d?log='+log_id
            link_to_pid_analysis_page = '?plots=pid_analysis&log='+log_id

            try:
                plots = generate_plots(ulog, px4_ulog, db_data, vehicle_data,
                                       link_to_3d_page, link_to_pid_analysis_page)

                title = 'Flight Review - '+px4_ulog.get_mav_type()

            except Exception as error:
                # catch all errors to avoid showing a blank page. Note that if we
                # get here, there's a bug somewhere that needs to be fixed!
                traceback.print_exc()

                title, error_message, plots = show_exception_page()

    else:

        title = 'Error'

        div = Div(text="<h3>Error</h3><p>"+error_message+"</p>", width=int(plot_width*0.9))
        plots = [column(div, width=int(plot_width*0.9))]

    # layout
    layout = column(plots)
    curdoc().add_root(layout)
    curdoc().title = title

    print_timing("Plotting", start_time)
