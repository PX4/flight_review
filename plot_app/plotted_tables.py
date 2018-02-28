""" methods to generate various tables used in configured_plots.py """

from html import escape
from math import sqrt
import datetime

import numpy as np
from plotting import DataPlot, plot_flight_modes_background, DataPlotSpec
from config import plot_config, colors8, colors2, color_gray, colors3
from bokeh.layouts import widgetbox
from bokeh.models import ColumnDataSource, Range1d
from bokeh.models.widgets import DataTable, TableColumn, Div

from helper import (
    get_default_parameters, get_airframe_name,
    get_total_flight_time, error_labels_table
    )

#pylint: disable=consider-using-enumerate


def _get_vtol_means_per_mode(vtol_states, timestamps, data):
    """
    get the mean values separated by MC and FW mode for some
    data vector
    :return: tuple of (mean mc, mean fw)
    """
    vtol_state_index = 0
    current_vtol_state = -1
    sum_mc = 0
    counter_mc = 0
    sum_fw = 0
    counter_fw = 0
    for i in range(len(timestamps)):
        if timestamps[i] > vtol_states[vtol_state_index][0]:
            current_vtol_state = vtol_states[vtol_state_index][1]
            vtol_state_index += 1
        if current_vtol_state == 2: # FW
            sum_fw += data[i]
            counter_fw += 1
        elif current_vtol_state == 3: # MC
            sum_mc += data[i]
            counter_mc += 1
    mean_mc = None
    if counter_mc > 0: mean_mc = sum_mc / counter_mc
    mean_fw = None
    if counter_fw > 0: mean_fw = sum_fw / counter_fw
    return (mean_mc, mean_fw)



def get_heading_and_info(ulog, px4_ulog, plot_width, db_data, vehicle_data,
                         vtol_states, link_to_3d_page):
    """
    get a bokeh widgetbox object with the html heading text and some tables with
    additional text info, such as logging duration, max speed etc.
    """

    # Heading
    sys_name = ''
    if 'sys_name' in ulog.msg_info_dict:
        sys_name = escape(ulog.msg_info_dict['sys_name']) + ' '

    if any(elem.name == 'vehicle_global_position' for elem in ulog.data_list):
        link_to_3d = "<a class='btn btn-primary' href='"+link_to_3d_page+"'>Open 3D View</a>"
    else:
        link_to_3d = ''

    div = Div(text="<table width='100%'><tr><td><h1>"+sys_name + px4_ulog.get_mav_type()+
              "</h1></td><td align='right'>" + link_to_3d+"</td></tr></table>",
              width=int(plot_width*0.999))
    header_divs = [div]
    if db_data.description != '':
        div_descr = Div(text="<h4>"+db_data.description+"</h4>", width=int(plot_width*0.9))
        header_divs.append(div_descr)

    ### Setup the text for the left table with various information ###
    table_text_left = []

    # airframe
    airframe_name_tuple = get_airframe_name(ulog, True)
    if airframe_name_tuple is not None:
        airframe_name, airframe_id = airframe_name_tuple
        if len(airframe_name) == 0:
            table_text_left.append(('Airframe', airframe_id))
        else:
            table_text_left.append(('Airframe', airframe_name+' <small>('+airframe_id+')</small>'))


    # HW & SW
    sys_hardware = ''
    if 'ver_hw' in ulog.msg_info_dict:
        sys_hardware = escape(ulog.msg_info_dict['ver_hw'])
        table_text_left.append(('Hardware', sys_hardware))

    release_str = ulog.get_version_info_str()
    if release_str is None:
        release_str = ''
        release_str_suffix = ''
    else:
        release_str += ' <small>('
        release_str_suffix = ')</small>'
    branch_info = ''
    if 'ver_sw_branch' in ulog.msg_info_dict:
        branch_info = '<br> branch: '+ulog.msg_info_dict['ver_sw_branch']
    if 'ver_sw' in ulog.msg_info_dict:
        ver_sw = escape(ulog.msg_info_dict['ver_sw'])
        ver_sw_link = 'https://github.com/PX4/Firmware/commit/'+ver_sw
        table_text_left.append(('Software Version', release_str +
                                '<a href="'+ver_sw_link+'" target="_blank">'+ver_sw[:8]+'</a>'+
                                release_str_suffix+branch_info))

    if 'sys_os_name' in ulog.msg_info_dict and 'sys_os_ver_release' in ulog.msg_info_dict:
        os_name = escape(ulog.msg_info_dict['sys_os_name'])
        os_ver = ulog.get_version_info_str('sys_os_ver_release')
        if os_ver is not None:
            table_text_left.append(('OS Version', os_name + ', ' + os_ver))

    table_text_left.append(('Estimator', px4_ulog.get_estimator()))

    table_text_left.append(('', '')) # spacing

    # logging start time & date
    try:
        # get the first non-zero timestamp
        gps_data = ulog.get_dataset('vehicle_gps_position')
        indices = np.nonzero(gps_data.data['time_utc_usec'])
        if len(indices[0]) > 0:
            # we use the timestamp from the log and then convert it with JS to
            # display with local timezone.
            # In addition we add a tooltip to show the timezone from the log
            logging_start_time = int(gps_data.data['time_utc_usec'][indices[0][0]] / 1000000)

            utc_offset_min = ulog.initial_parameters.get('SDLOG_UTC_OFFSET', 0)
            utctimestamp = datetime.datetime.utcfromtimestamp(
                logging_start_time+utc_offset_min*60).replace(tzinfo=datetime.timezone.utc)

            tooltip = '''This is your local timezone.
<br />
Log timezone: {}
<br />
SDLOG_UTC_OFFSET: {}'''.format(utctimestamp.strftime('%d-%m-%Y %H:%M'), utc_offset_min)
            tooltip = 'data-toggle="tooltip" data-delay=\'{"show":0, "hide":100}\' '+ \
                'title="'+tooltip+'" '
            table_text_left.append(
                ('Logging Start '+
                 '<i '+tooltip+' class="fa fa-question" aria-hidden="true" '+
                 'style="font-size: larger; color:#666"></i>',
                 '<span style="display:none" id="logging-start-element">'+
                 str(logging_start_time)+'</span>'))
    except:
        # Ignore. Eg. if topic not found
        pass


    # logging duration
    m, s = divmod(int((ulog.last_timestamp - ulog.start_timestamp)/1e6), 60)
    h, m = divmod(m, 60)
    table_text_left.append(('Logging Duration', '{:d}:{:02d}:{:02d}'.format(h, m, s)))

    # dropouts
    dropout_durations = [dropout.duration for dropout in ulog.dropouts]
    if len(dropout_durations) > 0:
        total_duration = sum(dropout_durations) / 1000
        if total_duration > 5:
            total_duration_str = '{:.0f}'.format(total_duration)
        else:
            total_duration_str = '{:.2f}'.format(total_duration)
        table_text_left.append(('Dropouts', '{:} ({:} s)'.format(
            len(dropout_durations), total_duration_str)))

    # total vehicle flight time
    flight_time_s = get_total_flight_time(ulog)
    if flight_time_s is not None:
        m, s = divmod(int(flight_time_s), 60)
        h, m = divmod(m, 60)
        days, h = divmod(h, 24)
        flight_time_str = ''
        if days > 0: flight_time_str += '{:d} days '.format(days)
        if h > 0: flight_time_str += '{:d} hours '.format(h)
        if m > 0: flight_time_str += '{:d} minutes '.format(m)
        flight_time_str += '{:d} seconds '.format(s)
        table_text_left.append(('Vehicle Life<br/>Flight Time', flight_time_str))

    table_text_left.append(('', '')) # spacing

    # vehicle UUID (and name if provided). SITL does not have a UUID
    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL':
        sys_uuid = escape(ulog.msg_info_dict['sys_uuid'])
        if vehicle_data is not None and vehicle_data.name != '':
            sys_uuid = sys_uuid + ' (' + vehicle_data.name + ')'
        if len(sys_uuid) > 0:
            table_text_left.append(('Vehicle UUID', sys_uuid))


    table_text_left.append(('', '')) # spacing

    # Wind speed, rating, feedback
    if db_data.wind_speed >= 0:
        table_text_left.append(('Wind Speed', db_data.wind_speed_str()))
    if len(db_data.rating) > 0:
        table_text_left.append(('Flight Rating', db_data.rating_str()))
    if len(db_data.feedback) > 0:
        table_text_left.append(('Feedback', db_data.feedback.replace('\n', '<br/>')))
    if len(db_data.video_url) > 0:
        table_text_left.append(('Video', '<a href="'+db_data.video_url+
                                '" target="_blank">'+db_data.video_url+'</a>'))


    ### Setup the text for the right table: estimated numbers (e.g. max speed) ###
    table_text_right = []
    try:

        local_pos = ulog.get_dataset('vehicle_local_position')
        pos_x = local_pos.data['x']
        pos_y = local_pos.data['y']
        pos_z = local_pos.data['z']
        pos_xyz_valid = np.multiply(local_pos.data['xy_valid'], local_pos.data['z_valid'])
        local_vel_valid_indices = np.argwhere(np.multiply(local_pos.data['v_xy_valid'],
                                                          local_pos.data['v_z_valid']) > 0)
        vel_x = local_pos.data['vx'][local_vel_valid_indices]
        vel_y = local_pos.data['vy'][local_vel_valid_indices]
        vel_z = local_pos.data['vz'][local_vel_valid_indices]

        # total distance (take only valid indexes)
        total_dist_m = 0
        last_index = -2
        for valid_index in np.argwhere(pos_xyz_valid > 0):
            index = valid_index[0]
            if index == last_index + 1:
                dx = pos_x[index] - pos_x[last_index]
                dy = pos_y[index] - pos_y[last_index]
                dz = pos_z[index] - pos_z[last_index]
                total_dist_m += sqrt(dx*dx + dy*dy + dz*dz)
            last_index = index
        if total_dist_m < 1:
            pass # ignore
        elif total_dist_m > 1000:
            table_text_right.append(('Distance', "{:.2f} km".format(total_dist_m/1000)))
        else:
            table_text_right.append(('Distance', "{:.1f} m".format(total_dist_m)))

        if len(pos_z) > 0:
            max_alt_diff = np.amax(pos_z) - np.amin(pos_z)
            table_text_right.append(('Max Altitude Difference', "{:.0f} m".format(max_alt_diff)))

        table_text_right.append(('', '')) # spacing

        # Speed
        if len(vel_x) > 0:
            max_h_speed = np.amax(np.sqrt(np.square(vel_x) + np.square(vel_y)))
            speed_vector = np.sqrt(np.square(vel_x) + np.square(vel_y) + np.square(vel_z))
            max_speed = np.amax(speed_vector)
            if vtol_states is None:
                mean_speed = np.mean(speed_vector)
                table_text_right.append(('Average Speed', "{:.1f} km/h".format(mean_speed*3.6)))
            else:
                local_pos_timestamp = local_pos.data['timestamp'][local_vel_valid_indices]
                speed_vector = speed_vector.reshape((len(speed_vector),))
                mean_speed_mc, mean_speed_fw = _get_vtol_means_per_mode(
                    vtol_states, local_pos_timestamp, speed_vector)
                if mean_speed_mc is not None:
                    table_text_right.append(
                        ('Average Speed MC', "{:.1f} km/h".format(mean_speed_mc*3.6)))
                if mean_speed_fw is not None:
                    table_text_right.append(
                        ('Average Speed FW', "{:.1f} km/h".format(mean_speed_fw*3.6)))
            table_text_right.append(('Max Speed', "{:.1f} km/h".format(max_speed*3.6)))
            table_text_right.append(('Max Speed Horizontal', "{:.1f} km/h".format(max_h_speed*3.6)))
            table_text_right.append(('Max Speed Up', "{:.1f} km/h".format(np.amax(-vel_z)*3.6)))
            table_text_right.append(('Max Speed Down', "{:.1f} km/h".format(-np.amin(-vel_z)*3.6)))

            table_text_right.append(('', '')) # spacing

        vehicle_attitude = ulog.get_dataset('vehicle_attitude')
        roll = vehicle_attitude.data['roll']
        pitch = vehicle_attitude.data['pitch']
        if len(roll) > 0:
            # tilt = angle between [0,0,1] and [0,0,1] rotated by roll and pitch
            tilt_angle = np.arccos(np.multiply(np.cos(pitch), np.cos(roll)))*180/np.pi
            table_text_right.append(('Max Tilt Angle', "{:.1f} deg".format(np.amax(tilt_angle))))

        rollspeed = vehicle_attitude.data['rollspeed']
        pitchspeed = vehicle_attitude.data['pitchspeed']
        yawspeed = vehicle_attitude.data['yawspeed']
        if len(rollspeed) > 0:
            max_rot_speed = np.amax(np.sqrt(np.square(rollspeed) +
                                            np.square(pitchspeed) +
                                            np.square(yawspeed)))
            table_text_right.append(('Max Rotation Speed', "{:.1f} deg/s".format(
                max_rot_speed*180/np.pi)))

        table_text_right.append(('', '')) # spacing

        battery_status = ulog.get_dataset('battery_status')
        battery_current = battery_status.data['current_a']
        if len(battery_current) > 0:
            max_current = np.amax(battery_current)
            if max_current > 0.1:
                if vtol_states is None:
                    mean_current = np.mean(battery_current)
                    table_text_right.append(('Average Current', "{:.1f} A".format(mean_current)))
                else:
                    mean_current_mc, mean_current_fw = _get_vtol_means_per_mode(
                        vtol_states, battery_status.data['timestamp'], battery_current)
                    if mean_current_mc is not None:
                        table_text_right.append(
                            ('Average Current MC', "{:.1f} A".format(mean_current_mc)))
                    if mean_current_fw is not None:
                        table_text_right.append(
                            ('Average Current FW', "{:.1f} A".format(mean_current_fw)))

                table_text_right.append(('Max Current', "{:.1f} A".format(max_current)))
    except:
        pass # ignore (e.g. if topic not found)


    # generate the tables
    def generate_html_table(rows_list, tooltip=None, max_width=None):
        """
        return the html table (str) from a row list of tuples
        """
        if tooltip is None:
            tooltip = ''
        else:
            tooltip = 'data-toggle="tooltip" data-placement="left" '+ \
                'data-delay=\'{"show": 1000, "hide": 100}\' title="'+tooltip+'" '
        table = '<table '+tooltip
        if max_width is not None:
            table += ' style="max-width: '+max_width+';"'
        table += '>'
        padding_text = ''
        for label, value in rows_list:
            if label == '': # empty label means: add some row spacing
                padding_text = ' style="padding-top: 0.5em;" '
            else:
                table += ('<tr><td '+padding_text+'class="left">'+label+
                          ':</td><td'+padding_text+'>'+value+'</td></tr>')
                padding_text = ''
        return table + '</table>'

    left_table = generate_html_table(table_text_left, max_width='65%')
    right_table = generate_html_table(
        table_text_right,
        'Note: most of these values are based on estimations from the vehicle,'
        ' and thus requiring an accurate estimator')
    html_tables = ('<div style="display: flex; justify-content: space-between;">'+
                   left_table+right_table+'</div>')

    header_divs.append(Div(text=html_tables))

    # add error label select after table
    error_label_select = '' \
        '<select id="error-label" class="chosen-select" multiple="True" '\
        'style="display: flex; " tabindex="-1" ' \
        'data-placeholder="Add a detected error..." " >'
    for err_id, err_label in error_labels_table.items():
        error_label_select += '<option data-id="{:d}">{:s}</option>'.format(err_id, err_label)
    error_label_select += '</select>'

    header_divs.append(Div(text=error_label_select))

    return widgetbox(header_divs, width=int(plot_width*0.99))


def get_changed_parameters(initial_parameters, plot_width):
    """
    get a bokeh widgetbox object with a table of the changed parameters
    :param initial_parameters: ulog.initial_parameters
    """
    param_names = []
    param_values = []
    param_defaults = []
    param_mins = []
    param_maxs = []
    param_descriptions = []
    default_params = get_default_parameters()
    for param_name in sorted(initial_parameters):
        param_value = initial_parameters[param_name]

        if param_name.startswith('RC') or param_name.startswith('CAL_'):
            continue

        try:
            if param_name in default_params:
                default_param = default_params[param_name]
                if default_param['type'] == 'FLOAT':
                    is_default = abs(float(default_param['default']) - float(param_value)) < 0.00001
                    if 'decimal' in default_param:
                        param_value = round(param_value, int(default_param['decimal']))
                else:
                    is_default = int(default_param['default']) == int(param_value)
                if not is_default:
                    param_names.append(param_name)
                    param_values.append(param_value)
                    param_defaults.append(default_param['default'])
                    param_mins.append(default_param.get('min', ''))
                    param_maxs.append(default_param.get('max', ''))
                    param_descriptions.append(default_param.get('short_desc', ''))
            else:
                # not found: add it as if it were changed
                param_names.append(param_name)
                param_values.append(param_value)
                param_defaults.append('')
                param_mins.append('')
                param_maxs.append('')
                param_descriptions.append('(unknown)')
        except Exception as error:
            print(type(error), error)
    param_data = dict(
        names=param_names,
        values=param_values,
        defaults=param_defaults,
        mins=param_mins,
        maxs=param_maxs,
        descriptions=param_descriptions)
    source = ColumnDataSource(param_data)
    columns = [
        TableColumn(field="names", title="Name",
                    width=int(plot_width*0.2), sortable=False),
        TableColumn(field="values", title="Value",
                    width=int(plot_width*0.15), sortable=False),
        TableColumn(field="defaults", title="Default",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="mins", title="Min",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="maxs", title="Max",
                    width=int(plot_width*0.075), sortable=False),
        TableColumn(field="descriptions", title="Description",
                    width=int(plot_width*0.40), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False)
    div = Div(text="""<b>Non-default Parameters</b> (except RC and sensor calibration)""",
              width=int(plot_width/2))
    return widgetbox(div, data_table, width=plot_width)


def get_logged_messages(logged_messages, plot_width):
    """
    get a bokeh widgetbox object with a table of the logged text messages
    :param logged_messages: ulog.logged_messages
    """
    log_times = []
    log_levels = []
    log_messages = []
    for m in logged_messages:
        m1, s1 = divmod(int(m.timestamp/1e6), 60)
        h1, m1 = divmod(m1, 60)
        log_times.append("{:d}:{:02d}:{:02d}".format(h1, m1, s1))
        log_levels.append(m.log_level_str())
        log_messages.append(m.message)
    log_data = dict(
        times=log_times,
        levels=log_levels,
        messages=log_messages)
    source = ColumnDataSource(log_data)
    columns = [
        TableColumn(field="times", title="Time",
                    width=int(plot_width*0.15), sortable=False),
        TableColumn(field="levels", title="Level",
                    width=int(plot_width*0.1), sortable=False),
        TableColumn(field="messages", title="Message",
                    width=int(plot_width*0.75), sortable=False),
        ]
    data_table = DataTable(source=source, columns=columns, width=plot_width,
                           height=300, sortable=False, selectable=False)
    div = Div(text="""<b>Logged Messages</b>""", width=int(plot_width/2))
    return widgetbox(div, data_table, width=plot_width)

def get_time_series_plots(flight_mode_changes, ulog, px4_ulog, plot_width, db_data, vehicle_data,
                         vtol_states, linkXAxes):

    plots = []
    data = ulog.data_list
    
    # initialize parameter changes
    changed_params = None
    if not 'replay' in ulog.msg_info_dict: # replay can have many param changes
        if len(ulog.changed_parameters) > 0:
            changed_params = ulog.changed_parameters
            plots.append(None) # save space for the param change button

    ### Add all data plots ###

    x_range_offset = (ulog.last_timestamp - ulog.start_timestamp) * 0.05
    x_range = Range1d(ulog.start_timestamp - x_range_offset, ulog.last_timestamp + x_range_offset)


    # Altitude estimate
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_axis_label='[m]', title='Altitude Estimate',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph([lambda data: ('alt', data['alt']*0.001)],
                        colors8[0:1], ['GPS Altitude'])
    data_plot.change_dataset('sensor_combined')
    data_plot.add_graph(['baro_alt_meter'], colors8[1:2], ['Barometer Altitude'])
    data_plot.change_dataset('vehicle_global_position')
    data_plot.add_graph(['alt'], colors8[2:3], ['Fused Altitude Estimation'])
    data_plot.change_dataset('position_setpoint_triplet')
    data_plot.add_circle(['current.alt'], [plot_config['mission_setpoint_color']],
                         ['Altitude Setpoint'])
    data_plot.change_dataset('actuator_controls_0')
    data_plot.add_graph([lambda data: ('thrust', data['control[3]']*100)],
                        colors8[6:7], ['Thrust [0, 100]'])
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

    if data_plot.finalize() is not None: plots.append(data_plot)



    # Roll/Pitch/Yaw angle & angular rate
    for axis in ['roll', 'pitch', 'yaw']:

        # angle
        axis_name = axis.capitalize()
        data_plot = DataPlot(data, plot_config, 'vehicle_attitude',
                             y_axis_label='[deg]', title=axis_name+' Angle',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            colors2[0:1], [axis_name+' Estimated'], mark_nan=True)
        data_plot.change_dataset('vehicle_attitude_setpoint')
        data_plot.add_graph([lambda data: (axis+'_d', np.rad2deg(data[axis+'_d']))],
                            colors2[1:2], [axis_name+' Setpoint'],
                            mark_nan=True, use_step_lines=True)
        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            [color_gray], [axis_name+' Groundtruth'])
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)

        # rate
        data_plot = DataPlot(data, plot_config, 'vehicle_attitude',
                             y_axis_label='[deg/s]', title=axis_name+' Angular Rate',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph([lambda data: (axis+'speed', np.rad2deg(data[axis+'speed']))],
                            colors2[0:1], [axis_name+' Rate Estimated'], mark_nan=True)
        data_plot.change_dataset('vehicle_rates_setpoint')
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            colors2[1:2], [axis_name+' Rate Setpoint'],
                            mark_nan=True, use_step_lines=True)
        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: (axis+'speed', np.rad2deg(data[axis+'speed']))],
                            [color_gray], [axis_name+' Rate Groundtruth'])
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)



    # Local position
    for axis in ['x', 'y', 'z']:
        data_plot = DataPlot(data, plot_config, 'vehicle_local_position',
                             y_axis_label='[m]', title='Local Position '+axis.upper(),
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph([axis], colors2[0:1], [axis.upper()+' Estimated'], mark_nan=True)
        data_plot.change_dataset('vehicle_local_position_setpoint')
        data_plot.add_graph([axis], colors2[1:2], [axis.upper()+' Setpoint'],
                            mark_nan=True, use_step_lines=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)



    # Velocity
    data_plot = DataPlot(data, plot_config, 'vehicle_local_position',
                         y_axis_label='[m/s]', title='Velocity',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['vx', 'vy', 'vz'], colors3, ['X', 'Y', 'Z'])
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

    if data_plot.finalize() is not None: plots.append(data_plot)


    # Vision position (only if topic found)
    if any(elem.name == 'vehicle_vision_position' for elem in data):
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_position',
                             y_axis_label='[m]', title='Vision Position',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(['x', 'y', 'z'], colors3, ['X', 'Y', 'Z'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['x', 'y', 'z'], colors8[2:5],
                            ['Groundtruth X', 'Groundtruth Y', 'Groundtruth Z'])

        if data_plot.finalize() is not None: plots.append(data_plot)


        # Vision velocity
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_position',
                             y_axis_label='[m]', title='Vision Velocity',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(['vx', 'vy', 'vz'], colors3, ['X', 'Y', 'Z'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['vx', 'vy', 'vz'], colors8[2:5],
                            ['Groundtruth X', 'Groundtruth Y', 'Groundtruth Z'])
        if data_plot.finalize() is not None: plots.append(data_plot)


    # Vision attitude
    if any(elem.name == 'vehicle_vision_attitude' for elem in data):
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_attitude',
                             y_axis_label='[deg]', title='Vision Attitude',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph([lambda data: ('roll', np.rad2deg(data['roll'])),
                             lambda data: ('pitch', np.rad2deg(data['pitch'])),
                             lambda data: ('yaw', np.rad2deg(data['yaw']))],
                            colors3, ['Roll', 'Pitch', 'Yaw'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: ('roll', np.rad2deg(data['roll'])),
                             lambda data: ('pitch', np.rad2deg(data['pitch'])),
                             lambda data: ('yaw', np.rad2deg(data['yaw']))],
                            colors8[2:5],
                            ['Roll Groundtruth', 'Pitch Groundtruth', 'Yaw Groundtruth'])

        if data_plot.finalize() is not None: plots.append(data_plot)


    # Airspeed vs Ground speed: but only if there's valid airspeed data
    try:
        cur_dataset = ulog.get_dataset('airspeed')
        if np.amax(cur_dataset.data['indicated_airspeed_m_s']) > 0.1:
            data_plot = DataPlot(data, plot_config, 'vehicle_global_position',
                                 y_axis_label='[m/s]', title='Airspeed',
                                 plot_height='small',
                                 changed_params=changed_params, x_range=x_range)
            data_plot.add_graph([lambda data: ('groundspeed_estimated',
                                               np.sqrt(data['vel_n']**2 + data['vel_e']**2))],
                                colors3[2:3], ['Ground Speed Estimated'])
            data_plot.change_dataset('airspeed')
            data_plot.add_graph(['indicated_airspeed_m_s'], colors2[0:1], ['Airspeed Indicated'])

            plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

            if data_plot.finalize() is not None: plots.append(data_plot)
    except (KeyError, IndexError) as error:
        pass



    # manual control inputs
    # prefer the manual_control_setpoint topic. Old logs do not contain it
    if any(elem.name == 'manual_control_setpoint' for elem in data):
        data_plot = DataPlot(data, plot_config, 'manual_control_setpoint',
                             title='Manual Control Inputs (Radio or Joystick)',
                             plot_height='small', y_range=Range1d(-1.1, 1.1),
                             changed_params=changed_params, x_range=x_range)
        data_plot.add_graph(['y', 'x', 'r', 'z',
                             lambda data: ('mode_slot', data['mode_slot']/6),
                             'aux1', 'aux2',
                             lambda data: ('kill_switch', data['kill_switch'] == 1)],
                            colors8,
                            ['Y / Roll', 'X / Pitch', 'Yaw', 'Throttle [0, 1]',
                             'Flight Mode', 'Aux1', 'Aux2', 'Kill Switch'])
        # TODO: add RTL switch and others? Look at params which functions are mapped?
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)

    else: # it's an old log
        data_plot = DataPlot(data, plot_config, 'rc_channels',
                             title='Raw Radio Control Inputs',
                             plot_height='small', y_range=Range1d(-1.1, 1.1),
                             changed_params=changed_params, x_range=x_range)
        num_rc_channels = 8
        if data_plot.dataset:
            max_channels = np.amax(data_plot.dataset.data['channel_count'])
            if max_channels < num_rc_channels: num_rc_channels = max_channels
        legends = []
        for i in range(num_rc_channels):
            channel_names = px4_ulog.get_configured_rc_input_names(i)
            if channel_names is None:
                legends.append('Channel '+str(i))
            else:
                legends.append('Channel '+str(i)+' ('+', '.join(channel_names)+')')
        data_plot.add_graph(['channels['+str(i)+']' for i in range(num_rc_channels)],
                            colors8[0:num_rc_channels], legends, mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)



    # actuator controls 0
    data_plot = DataPlot(data, plot_config, 'actuator_controls_0',
                         y_start=0, title='Actuator Controls 0', plot_height='small',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph(['control[0]', 'control[1]', 'control[2]', 'control[3]'],
                        colors8[0:4], ['Roll', 'Pitch', 'Yaw', 'Thrust'], mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)

    # actuator controls 1
    # (only present on VTOL, Fixed-wing config)
    data_plot = DataPlot(data, plot_config, 'actuator_controls_1',
                         y_start=0, title='Actuator Controls 1 (VTOL in Fixed-Wing mode)',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['control[0]', 'control[1]', 'control[2]', 'control[3]'],
                        colors8[0:4], ['Roll', 'Pitch', 'Yaw', 'Thrust'], mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)


    # actuator outputs 0: Main
    data_plot = DataPlot(data, plot_config, 'actuator_outputs',
                         y_start=0, title='Actuator Outputs (Main)', plot_height='small',
                         changed_params=changed_params, x_range=x_range)
    num_actuator_outputs = 8
    if data_plot.dataset:
        max_outputs = np.amax(data_plot.dataset.data['noutputs'])
        if max_outputs < num_actuator_outputs: num_actuator_outputs = max_outputs
    data_plot.add_graph(['output['+str(i)+']' for i in
                         range(num_actuator_outputs)], colors8[0:num_actuator_outputs],
                        ['Output '+str(i) for i in range(num_actuator_outputs)], mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

    if data_plot.finalize() is not None: plots.append(data_plot)

    # actuator outputs 1: AUX
    data_plot = DataPlot(data, plot_config, 'actuator_outputs',
                         y_start=0, title='Actuator Outputs (AUX)', plot_height='small',
                         changed_params=changed_params, topic_instance=1,
                         x_range=x_range)
    num_actuator_outputs = 8
    # only plot if at least one of the outputs is not constant
    all_constant = True
    if data_plot.dataset:
        max_outputs = np.amax(data_plot.dataset.data['noutputs'])
        if max_outputs < num_actuator_outputs: num_actuator_outputs = max_outputs

        for i in range(num_actuator_outputs):
            output_data = data_plot.dataset.data['output['+str(i)+']']
            if not np.all(output_data == output_data[0]):
                all_constant = False
    if not all_constant:
        data_plot.add_graph(['output['+str(i)+']' for i in
                             range(num_actuator_outputs)], colors8[0:num_actuator_outputs],
                            ['Output '+str(i) for i in range(num_actuator_outputs)], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)


    # raw acceleration
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[m/s^2]', title='Raw Acceleration',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['accelerometer_m_s2[0]', 'accelerometer_m_s2[1]',
                         'accelerometer_m_s2[2]'], colors3, ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # raw angular speed
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[deg/s]', title='Raw Angular Speed (Gyroscope)',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph([
        lambda data: ('gyro_rad[0]', np.rad2deg(data['gyro_rad[0]'])),
        lambda data: ('gyro_rad[1]', np.rad2deg(data['gyro_rad[1]'])),
        lambda data: ('gyro_rad[2]', np.rad2deg(data['gyro_rad[2]']))],
                        colors3, ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # magnetic field strength
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[gauss]', title='Raw Magnetic Field Strength',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['magnetometer_ga[0]', 'magnetometer_ga[1]',
                         'magnetometer_ga[2]'], colors3,
                        ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # distance sensor
    data_plot = DataPlot(data, plot_config, 'distance_sensor',
                         y_start=0, y_axis_label='[m]', title='Distance Sensor',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['current_distance', 'covariance'], colors3[0:2],
                        ['Distance', 'Covariance'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # gps uncertainty
    # the accuracy values can be really large if there is no fix, so we limit the
    # y axis range to some sane values
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         title='GPS Uncertainty', y_range=Range1d(0, 40),
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['eph', 'epv', 'satellites_used', 'fix_type'], colors8[::2],
                        ['Horizontal position accuracy [m]', 'Vertical position accuracy [m]',
                         'Num Satellites used', 'GPS Fix'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # gps noise & jamming
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_start=0, title='GPS Noise & Jamming',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['noise_per_ms', 'jamming_indicator'], colors3[0:2],
                        ['Noise per ms', 'Jamming Indicator'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # thrust and magnetic field
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_start=0, title='Thrust and Magnetic Field', plot_height='small',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph(
        [lambda data: ('len_mag', np.sqrt(data['magnetometer_ga[0]']**2 +
                                          data['magnetometer_ga[1]']**2 +
                                          data['magnetometer_ga[2]']**2))],
        colors2[0:1], ['Norm of Magnetic Field'])
    data_plot.change_dataset('actuator_controls_0')
    data_plot.add_graph([lambda data: ('thrust', data['control[3]'])],
                        colors2[1:2], ['Thrust'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # Acceleration Spectrogram
    data_plot = DataPlotSpec(data, plot_config, 'sensor_combined',
                             y_axis_label='[Hz]', title='Acceleration Power Spectral Density',
                             plot_height='small', x_range=x_range)
    data_plot.add_graph(['accelerometer_m_s2[0]', 'accelerometer_m_s2[1]', 'accelerometer_m_s2[2]'],
                        ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)

    # power
    data_plot = DataPlot(data, plot_config, 'battery_status',
                         y_start=0, title='Power',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['voltage_v', 'voltage_filtered_v',
                         'current_a', lambda data: ('discharged_mah', data['discharged_mah']/100),
                         lambda data: ('remaining', data['remaining']*10)],
                        colors8[::2]+colors8[1:2],
                        ['Voltage [V]', 'Voltage filtered [V]', 'Current [A]',
                         'Discharged Amount [mAh / 100]', 'Battery remaining [0=empty, 10=full]'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # estimator watchdog
    try:
        data_plot = DataPlot(data, plot_config, 'estimator_status',
                             y_start=0, title='Estimator Watchdog',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        estimator_status = ulog.get_dataset('estimator_status').data
        plot_data = []
        plot_labels = []
        input_data = [
            ('NaN Flags', estimator_status['nan_flags']),
            ('Health Flags (vel, pos, hgt)', estimator_status['health_flags']),
            ('Timeout Flags (vel, pos, hgt)', estimator_status['timeout_flags']),
            ('Velocity Check Bit', (estimator_status['innovation_check_flags'])&0x1),
            ('Horizontal Position Check Bit', (estimator_status['innovation_check_flags']>>1)&1),
            ('Vertical Position Check Bit', (estimator_status['innovation_check_flags']>>2)&1),
            ('Mag X, Y, Z Check Bits', (estimator_status['innovation_check_flags']>>3)&0x7),
            ('Yaw Check Bit', (estimator_status['innovation_check_flags']>>6)&1),
            ('Airspeed Check Bit', (estimator_status['innovation_check_flags']>>7)&1),
            ('Synthetic Sideslip Check Bit', (estimator_status['innovation_check_flags']>>8)&1),
            ('Height to Ground Check Bit', (estimator_status['innovation_check_flags']>>9)&1),
            ('Optical Flow X, Y Check Bits', (estimator_status['innovation_check_flags']>>10)&0x3),
            ]
        # filter: show only the flags that have non-zero samples
        for cur_label, cur_data in input_data:
            if np.amax(cur_data) > 0.1:
                data_label = 'flags_'+str(len(plot_data)) # just some unique string
                plot_data.append(lambda d, data=cur_data, label=data_label: (label, data))
                plot_labels.append(cur_label)
                if len(plot_data) >= 8: # cannot add more than that
                    break

        if len(plot_data) == 0:
            # add the plot even in the absence of any problem, so that the user
            # can validate that (otherwise it's ambiguous: it could be that the
            # estimator_status topic is not logged)
            plot_data = [lambda d: ('flags', input_data[0][1])]
            plot_labels = [input_data[0][0]]
        data_plot.add_graph(plot_data, colors8[0:len(plot_data)], plot_labels)
        if data_plot.finalize() is not None: plots.append(data_plot)
    except (KeyError, IndexError) as error:
        print('Error in estimator plot: '+str(error))



    # RC Quality
    data_plot = DataPlot(data, plot_config, 'input_rc',
                         title='RC Quality', plot_height='small', y_range=Range1d(0, 1),
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph([lambda data: ('rssi', data['rssi']/100), 'rc_lost'],
                        colors3[0:2], ['RSSI [0, 1]', 'RC Lost (Indicator)'])
    data_plot.change_dataset('vehicle_status')
    data_plot.add_graph(['rc_signal_lost'], colors3[2:3], ['RC Lost (Detected)'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # cpu load
    data_plot = DataPlot(data, plot_config, 'cpuload',
                         title='CPU & RAM', plot_height='small', y_range=Range1d(0, 1),
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph(['ram_usage', 'load'], [colors3[1], colors3[2]],
                        ['RAM Usage', 'CPU Load'])
    data_plot.add_span('load', line_color=colors3[2])
    data_plot.add_span('ram_usage', line_color=colors3[1])
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)


    # sampling: time difference
    try:
        data_plot = DataPlot(data, plot_config, 'sensor_combined', y_range=Range1d(0, 25e3),
                             y_axis_label='[us]',
                             title='Sampling Regularity of Sensor Data', plot_height='small',
                             changed_params=changed_params, x_range=x_range)
        sensor_combined = ulog.get_dataset('sensor_combined').data
        sampling_diff = np.diff(sensor_combined['timestamp'])
        min_sampling_diff = np.amin(sampling_diff)

        plot_dropouts(data_plot.bokeh_plot, ulog.dropouts, min_sampling_diff)

        data_plot.add_graph([lambda data: ('timediff', np.append(sampling_diff, 0))],
                            [colors3[2]], ['delta t (between 2 logged samples)'])
        data_plot.change_dataset('estimator_status')
        data_plot.add_graph([lambda data: ('time_slip', data['time_slip']*1e6)],
                            [colors3[1]], ['Estimator time slip (cumulative)'])
        if data_plot.finalize() is not None: plots.append(data_plot)
    except:
        pass

    return plots
