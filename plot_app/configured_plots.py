""" This contains the list of all drawn plots on the log plotting page """

from html import escape

from bokeh.layouts import widgetbox
from bokeh.models import Range1d
from bokeh.models.widgets import Div, Button
from bokeh.io import curdoc

from helper import *
from config import *
from plotting import *
from plotted_tables import (
    get_logged_messages, get_changed_parameters,
    get_info_table_html, get_heading_html, get_error_labels_html,
    get_hardfault_html
    )

#pylint: disable=cell-var-from-loop, undefined-loop-variable,
#pylint: disable=consider-using-enumerate,too-many-statements


def generate_plots(ulog, px4_ulog, db_data, vehicle_data, link_to_3d_page):
    """ create a list of bokeh plots (and widgets) to show """

    plots = []
    data = ulog.data_list

    # COMPATIBILITY support for old logs
    if any(elem.name == 'vehicle_air_data' or elem.name == 'vehicle_magnetometer' for elem in data):
        baro_alt_meter_topic = 'vehicle_air_data'
        magnetometer_ga_topic = 'vehicle_magnetometer'
    else: # old
        baro_alt_meter_topic = 'sensor_combined'
        magnetometer_ga_topic = 'sensor_combined'
    for topic in data:
        if topic.name == 'system_power':
            # COMPATIBILITY: rename fields to new format
            if 'voltage5V_v' in topic.data:     # old (prior to PX4/Firmware:213aa93)
                topic.data['voltage5v_v'] = topic.data.pop('voltage5V_v')
            if 'voltage3V3_v' in topic.data:    # old (prior to PX4/Firmware:213aa93)
                topic.data['voltage3v3_v'] = topic.data.pop('voltage3V3_v')

    # initialize flight mode changes
    flight_mode_changes = get_flight_mode_changes(ulog)

    # VTOL state changes & vehicle type
    is_multicopter = False # this is False for VTOLs as well
    vtol_states = None
    try:
        cur_dataset = ulog.get_dataset('vehicle_status')
        if np.amax(cur_dataset.data['is_vtol']) == 1:
            vtol_states = cur_dataset.list_value_changes('in_transition_mode')
            # find mode after transitions (states: 1=transition, 2=FW, 3=MC)
            for i in range(len(vtol_states)):
                if vtol_states[i][1] == 0:
                    t = vtol_states[i][0]
                    idx = np.argmax(cur_dataset.data['timestamp'] >= t) + 1
                    vtol_states[i] = (t, 2 + cur_dataset.data['is_rotary_wing'][idx])
            vtol_states.append((ulog.last_timestamp, -1))
        elif np.amax(cur_dataset.data['is_rotary_wing']) == 1:
            is_multicopter = True
    except (KeyError, IndexError) as error:
        vtol_states = None



    # Heading
    curdoc().template_variables['title_html'] = get_heading_html(
        ulog, px4_ulog, db_data, link_to_3d_page)

    # info text on top (logging duration, max speed, ...)
    curdoc().template_variables['info_table_html'] = \
        get_info_table_html(ulog, px4_ulog, db_data, vehicle_data, vtol_states)

    curdoc().template_variables['error_labels_html'] = get_error_labels_html()

    hardfault_html = get_hardfault_html(ulog)
    if hardfault_html is not None:
        curdoc().template_variables['hardfault_html'] = hardfault_html




# FIXME: for now, we use Google maps directly without bokeh, because it's not working reliably
    # GPS map
#    gps_plots = []
#    gps_titles = []
#    plot = plot_map(ulog, plot_config, map_type='google', api_key =
#            get_google_maps_api_key(), setpoints=False)
#    if plot is not None:
#        gps_plots.append(plot)
#        gps_titles.append('GPS Map: Satellite')
#
#    plot = plot_map(ulog, plot_config, map_type='plain', setpoints=True)
#    if plot is not None:
#        gps_plots.append(plot)
#        gps_titles.append('GPS Map: Plain')
#
#    data_plot = DataPlot2D(data, plot_config, 'vehicle_local_position',
#        x_axis_label = '[m]', y_axis_label='[m]', plot_height='large')
#    data_plot.add_graph('y', 'x', colors2[0], 'Estimated')
#    data_plot.change_dataset('vehicle_local_position_setpoint')
#    data_plot.add_graph('y', 'x', colors2[1], 'Setpoint')
#    if data_plot.finalize() is not None:
#        gps_plots.append(data_plot.bokeh_plot)
#        gps_titles.append('Local Position')
#
#    if len(gps_plots) >= 2:
#        tabs = []
#        for i in range(len(gps_plots)):
#            tabs.append(Panel(child=gps_plots[i], title=gps_titles[i]))
#        gps_plot_height=plot_config['plot_height']['large'] + 30
#        plots.append(Tabs(tabs=tabs, width=plot_width, height=gps_plot_height))
#    elif len(gps_plots) == 1:
#        plots.extend(gps_plots)


    if is_running_locally():
        # show the google maps plot via Bokeh, since the one in the html
        # template does not work locally (we disable it further down)
        map_plot = plot_map(ulog, plot_config, map_type='google', api_key=
                            get_google_maps_api_key(), setpoints=False)
        if map_plot is not None:
            plots.append(map_plot)


    # Position plot
    data_plot = DataPlot2D(data, plot_config, 'vehicle_local_position',
                           x_axis_label='[m]', y_axis_label='[m]', plot_height='large')
    data_plot.add_graph('y', 'x', colors2[0], 'Estimated',
                        check_if_all_zero=True)
    if not data_plot.had_error: # vehicle_local_position is required
        data_plot.change_dataset('vehicle_local_position_setpoint')
        data_plot.add_graph('y', 'x', colors2[1], 'Setpoint')
        # groundtruth (SITL only)
        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph('y', 'x', color_gray, 'Groundtruth')
        # GPS + position setpoints
        plot_map(ulog, plot_config, map_type='plain', setpoints=True,
                 bokeh_plot=data_plot.bokeh_plot)
        if data_plot.finalize() is not None:
            plots.append(data_plot.bokeh_plot)
            if not is_running_locally(): # do not enable Google Map if running locally
                curdoc().template_variables['has_position_data'] = True

    # initialize parameter changes
    changed_params = None
    if not 'replay' in ulog.msg_info_dict: # replay can have many param changes
        if len(ulog.changed_parameters) > 0:
            changed_params = ulog.changed_parameters
            plots.append(None) # save space for the param change button

    ### Add all data plots ###

    x_range_offset = (ulog.last_timestamp - ulog.start_timestamp) * 0.05
    x_range = Range1d(ulog.start_timestamp - x_range_offset, ulog.last_timestamp + x_range_offset)

    # Position focus
    lat_focus = (data[0].data.get('lat').tolist())[0]
    lon_focus = (data[0].data.get('lon').tolist())[0]
    lat_lon_focus = {'lat':lat_focus, 'lon':lon_focus}
    curdoc().template_variables['lat_lon_focus'] = lat_lon_focus

    # Altitude estimate
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_axis_label='[m]', title='Altitude Estimate',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph([lambda data: ('alt', data['alt']*0.001)],
                        colors8[0:1], ['GPS Altitude'])
    data_plot.change_dataset(baro_alt_meter_topic)
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
                            colors3[0:1], [axis_name+' Estimated'], mark_nan=True)
        data_plot.change_dataset('vehicle_attitude_setpoint')
        # in fixed-wing, the attitude setpoint is allowed to be NaN
        data_plot.add_graph([lambda data: (axis+'_d', np.rad2deg(data[axis+'_d']))],
                            colors3[1:2], [axis_name+' Setpoint'],
                            mark_nan=is_multicopter, use_step_lines=True)
        if axis == 'yaw':
            data_plot.add_graph(
                [lambda data: ('yaw_sp_move_rate', np.rad2deg(data['yaw_sp_move_rate']))],
                colors3[2:3], [axis_name+' FF Setpoint [deg/s]'],
                use_step_lines=True)
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
                            colors3[0:1], [axis_name+' Rate Estimated'], mark_nan=True)
        data_plot.change_dataset('vehicle_rates_setpoint')
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            colors3[1:2], [axis_name+' Rate Setpoint'],
                            mark_nan=True, use_step_lines=True)
        axis_letter = axis[0].upper()
        rate_int_limit = '(*100)'
        # this param is MC/VTOL only (it will not exist on FW)
        rate_int_limit_param = 'MC_' + axis_letter + 'R_INT_LIM'
        if rate_int_limit_param in ulog.initial_parameters:
            rate_int_limit = '[-{0:.0f}, {0:.0f}]'.format(
                ulog.initial_parameters[rate_int_limit_param]*100)
        data_plot.change_dataset('rate_ctrl_status')
        data_plot.add_graph([lambda data: (axis, data[axis+'speed_integ']*100)],
                            colors3[2:3], [axis_name+' Rate Integral '+rate_int_limit])
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
    data_plot.add_graph(['vx', 'vy', 'vz'], colors8[0:3], ['X', 'Y', 'Z'])
    data_plot.change_dataset('vehicle_local_position_setpoint')
    data_plot.add_graph(['vx', 'vy', 'vz'], [colors8[5], colors8[4], colors8[6]],
                        ['X Setpoint', 'Y Setpoint', 'Z Setpoint'], use_step_lines=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

    if data_plot.finalize() is not None: plots.append(data_plot)


    # Visual Odometry (only if topic found)
    if any(elem.name == 'vehicle_visual_odometry' for elem in data):
        # Vision position
        data_plot = DataPlot(data, plot_config, 'vehicle_visual_odometry',
                             y_axis_label='[m]', title='Visual Odometry Position',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(['x', 'y', 'z'], colors3, ['X', 'Y', 'Z'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['x', 'y', 'z'], colors8[2:5],
                            ['Groundtruth X', 'Groundtruth Y', 'Groundtruth Z'])

        if data_plot.finalize() is not None: plots.append(data_plot)


        # Vision velocity
        data_plot = DataPlot(data, plot_config, 'vehicle_visual_odometry',
                             y_axis_label='[m]', title='Visual Odometry Velocity',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(['vx', 'vy', 'vz'], colors3, ['X', 'Y', 'Z'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['vx', 'vy', 'vz'], colors8[2:5],
                            ['Groundtruth VX', 'Groundtruth VY', 'Groundtruth VZ'])
        if data_plot.finalize() is not None: plots.append(data_plot)


        # Vision attitude
        data_plot = DataPlot(data, plot_config, 'vehicle_visual_odometry',
                             y_axis_label='[deg]', title='Visual Odometry Attitude',
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

        # Vision attitude rate
        data_plot = DataPlot(data, plot_config, 'vehicle_visual_odometry',
                             y_axis_label='[deg]', title='Visual Odometry Attitude Rate',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph([lambda data: ('rollspeed', np.rad2deg(data['rollspeed'])),
                             lambda data: ('pitchspeed', np.rad2deg(data['pitchspeed'])),
                             lambda data: ('yawspeed', np.rad2deg(data['yawspeed']))],
                            colors3, ['Roll Rate', 'Pitch Rate', 'Yaw Rate'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: ('rollspeed', np.rad2deg(data['rollspeed'])),
                             lambda data: ('pitchspeed', np.rad2deg(data['pitchspeed'])),
                             lambda data: ('yawspeed', np.rad2deg(data['yawspeed']))],
                            colors8[2:5],
                            ['Roll Rate Groundtruth', 'Pitch Rate Groundtruth',
                             'Yaw Rate Groundtruth'])

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

    else: # it's an old log (COMPATIBILITY)
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

    # actuator controls (Main) FFT (for filter & output noise analysis)
    data_plot = DataPlotFFT(data, plot_config, 'actuator_controls_0',
                            title='Actuator Controls FFT')
    data_plot.add_graph(['control[0]', 'control[1]', 'control[2]'],
                        colors3, ['Roll', 'Pitch', 'Yaw'])
    if not data_plot.had_error:
        if 'MC_DTERM_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['MC_DTERM_CUTOFF'],
                'MC_DTERM_CUTOFF')
        if 'IMU_GYRO_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['IMU_GYRO_CUTOFF'],
                'IMU_GYRO_CUTOFF', 20)

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
    data_plot = DataPlot(data, plot_config, magnetometer_ga_topic,
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
    data_plot = DataPlot(data, plot_config, magnetometer_ga_topic,
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
                        ['Battery Voltage [V]', 'Battery Voltage filtered [V]',
                         'Battery Current [A]', 'Discharged Amount [mAh / 100]',
                         'Battery remaining [0=empty, 10=full]'])
    data_plot.change_dataset('system_power')
    if data_plot.dataset:
        if 'voltage5v_v' in data_plot.dataset.data and \
                        np.amax(data_plot.dataset.data['voltage5v_v']) > 0.0001:
            data_plot.add_graph(['voltage5v_v'], colors8[7:8], ['5 V'])
        if 'voltage3v3_v' in data_plot.dataset.data and \
                        np.amax(data_plot.dataset.data['voltage3v3_v']) > 0.0001:
            data_plot.add_graph(['voltage3v3_v'], colors8[5:6], ['3.3 V'])
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



    # exchange all DataPlot's with the bokeh_plot and handle parameter changes

    param_changes_button = Button(label="Hide Parameter Changes", width=170)
    param_change_labels = []
    # FIXME: this should be a CustomJS callback, not on the server. However this
    # did not work for me.
    def param_changes_button_clicked():
        """ callback to show/hide parameter changes """
        for label in param_change_labels:
            if label.visible:
                param_changes_button.label = 'Show Parameter Changes'
                label.visible = False
                label.text_alpha = 0 # label.visible does not work, so we use this instead
            else:
                param_changes_button.label = 'Hide Parameter Changes'
                label.visible = True
                label.text_alpha = 1
    param_changes_button.on_click(param_changes_button_clicked)


    jinja_plot_data = []
    for i in range(len(plots)):
        if plots[i] is None:
            plots[i] = widgetbox(param_changes_button, width=int(plot_width * 0.99))
        if isinstance(plots[i], DataPlot):
            if plots[i].param_change_label is not None:
                param_change_labels.append(plots[i].param_change_label)

            plot_title = plots[i].title
            plots[i] = plots[i].bokeh_plot

            fragment = 'Nav-'+plot_title.replace(' ', '-') \
                .replace('&', '_').replace('(', '').replace(')', '')
            jinja_plot_data.append({
                'model_id': plots[i].ref['id'],
                'fragment': fragment,
                'title': plot_title
                })


    # changed parameters
    plots.append(get_changed_parameters(ulog.initial_parameters, plot_width))



    # information about which messages are contained in the log
# TODO: need to load all topics for this (-> log loading will take longer)
#       but if we load all topics and the log contains some (external) topics
#       with buggy timestamps, it will affect the plotting.
#    data_list_sorted = sorted(ulog.data_list, key=lambda d: d.name + str(d.multi_id))
#    table_text = []
#    for d in data_list_sorted:
#        message_size = sum([ULog.get_field_size(f.type_str) for f in d.field_data])
#        num_data_points = len(d.data['timestamp'])
#        table_text.append((d.name, str(d.multi_id), str(message_size), str(num_data_points),
#           str(message_size * num_data_points)))
#    topics_info = '<table><tr><th>Name</th><th>Topic instance</th><th>Message Size</th>' \
#            '<th>Number of data points</th><th>Total bytes</th></tr>' + ''.join(
#            ['<tr><td>'+'</td><td>'.join(list(x))+'</td></tr>' for x in table_text]) + '</table>'
#    topics_div = Div(text=topics_info, width=int(plot_width*0.9))
#    plots.append(widgetbox(topics_div, width=int(plot_width*0.9)))


    # log messages
    plots.append(get_logged_messages(ulog.logged_messages, plot_width))


    # perf & top output
    top_data = ''
    perf_data = ''
    for state in ['pre', 'post']:
        if 'perf_top_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_top_data = ulog.msg_info_multiple_dict['perf_top_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_top_data))
            top_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'
        if 'perf_counter_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_perf_data = ulog.msg_info_multiple_dict['perf_counter_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_perf_data))
            perf_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'

    additional_data_html = ''
    if len(top_data) > 0:
        additional_data_html += '<h5>Processes</h5>'+top_data
    if len(perf_data) > 0:
        additional_data_html += '<h5>Performance Counters</h5>'+perf_data
    if len(additional_data_html) > 0:
        # hide by default & use a button to expand
        additional_data_html = '''
<button class="btn btn-secondary" data-toggle="collapse" style="min-width:0;"
 data-target="#show-additional-data">Show additional Data</button>
<div id="show-additional-data" class="collapse">
{:}
</div>
'''.format(additional_data_html)
        additional_data_div = Div(text=additional_data_html, width=int(plot_width*0.9))
        plots.append(widgetbox(additional_data_div, width=int(plot_width*0.9)))


    curdoc().template_variables['plots'] = jinja_plot_data

    return plots
