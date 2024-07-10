""" This contains the list of all drawn plots on the log plotting page """

import re
from html import escape

from bokeh.layouts import column
from bokeh.models import Range1d
from bokeh.models.widgets import Button
from bokeh.io import curdoc

from config import *
from helper import *
from leaflet import ulog_to_polyline
from plotting import *
from plotted_tables import (
    get_logged_messages, get_changed_parameters,
    get_info_table_html, get_heading_html, get_error_labels_html,
    get_hardfault_html, get_corrupt_log_html
    )

from vtol_tailsitter import *

#pylint: disable=cell-var-from-loop, undefined-loop-variable,
#pylint: disable=consider-using-enumerate,too-many-statements



def generate_plots(ulog, px4_ulog, db_data, vehicle_data, link_to_3d_page,
                   link_to_pid_analysis_page):
    """ create a list of bokeh plots (and widgets) to show """

    plots = []
    data = ulog.data_list

    # COMPATIBILITY support for old logs
    if any(elem.name in ('vehicle_air_data', 'vehicle_magnetometer') for elem in data):
        baro_alt_meter_topic = 'vehicle_air_data'
        magnetometer_ga_topic = 'vehicle_magnetometer'
    else: # old
        baro_alt_meter_topic = 'sensor_combined'
        magnetometer_ga_topic = 'sensor_combined'
    manual_control_sp_controls = ['roll', 'pitch', 'yaw', 'throttle']
    manual_control_sp_throttle_range = '[-1, 1]'
    vehicle_gps_position_altitude = None
    for topic in data:
        if topic.name == 'system_power':
            # COMPATIBILITY: rename fields to new format
            if 'voltage5V_v' in topic.data:     # old (prior to PX4/Firmware:213aa93)
                topic.data['voltage5v_v'] = topic.data.pop('voltage5V_v')
            if 'voltage3V3_v' in topic.data:    # old (prior to PX4/Firmware:213aa93)
                topic.data['sensors3v3[0]'] = topic.data.pop('voltage3V3_v')
            if 'voltage3v3_v' in topic.data:
                topic.data['sensors3v3[0]'] = topic.data.pop('voltage3v3_v')
        elif topic.name == 'tecs_status':
            if 'airspeed_sp' in topic.data: # old (prior to PX4-Autopilot/pull/16585)
                topic.data['true_airspeed_sp'] = topic.data.pop('airspeed_sp')
        elif topic.name == 'manual_control_setpoint':
            if 'throttle' not in topic.data: # old (prior to PX4-Autopilot/pull/15949)
                manual_control_sp_controls = ['y', 'x', 'r', 'z']
                manual_control_sp_throttle_range = '[0, 1]'
        elif topic.name == 'vehicle_gps_position':
            if ulog.msg_info_dict.get('ver_data_format', 0) >= 2:
                vehicle_gps_position_altitude = topic.data['altitude_msl_m']
            else: # COMPATIBILITY
                vehicle_gps_position_altitude = topic.data['alt'] * 0.001

    if any(elem.name == 'vehicle_angular_velocity' for elem in data):
        rate_estimated_topic_name = 'vehicle_angular_velocity'
        rate_groundtruth_topic_name = 'vehicle_angular_velocity_groundtruth'
        rate_field_names = ['xyz[0]', 'xyz[1]', 'xyz[2]']
    else: # old
        rate_estimated_topic_name = 'vehicle_attitude'
        rate_groundtruth_topic_name = 'vehicle_attitude_groundtruth'
        rate_field_names = ['rollspeed', 'pitchspeed', 'yawspeed']
    if any(elem.name == 'manual_control_switches' for elem in data):
        manual_control_switches_topic = 'manual_control_switches'
    else: # old
        manual_control_switches_topic = 'manual_control_setpoint'
    dynamic_control_alloc = any(elem.name in ('actuator_motors', 'actuator_servos')
                                for elem in data)
    actuator_controls_0 = ActuatorControls(ulog, dynamic_control_alloc, 0)
    actuator_controls_1 = ActuatorControls(ulog, dynamic_control_alloc, 1)

    # initialize flight mode changes
    flight_mode_changes = get_flight_mode_changes(ulog)

    # VTOL state changes & vehicle type
    vtol_states = None
    is_vtol = False
    is_vtol_tailsitter = False
    try:
        cur_dataset = ulog.get_dataset('vehicle_status')
        if np.amax(cur_dataset.data['is_vtol']) == 1:
            is_vtol = True
            # check if is tailsitter
            is_vtol_tailsitter = ('is_vtol_tailsitter' in cur_dataset.data and
                                  np.amax(cur_dataset.data['is_vtol_tailsitter']) == 1)
            # find mode after transitions (states: 1=transition, 2=FW, 3=MC)
            if 'vehicle_type' in cur_dataset.data:
                vehicle_type_field = 'vehicle_type'
                vtol_state_mapping = {2: 2, 1: 3}
                vehicle_type = cur_dataset.data['vehicle_type']
                in_transition_mode = cur_dataset.data['in_transition_mode']
                vtol_states = []
                for i in range(len(vehicle_type)):
                    # a VTOL can change state also w/o in_transition_mode set
                    # (e.g. in Manual mode)
                    if i == 0 or in_transition_mode[i-1] != in_transition_mode[i] or \
                        vehicle_type[i-1] != vehicle_type[i]:
                        vtol_states.append((cur_dataset.data['timestamp'][i],
                                            in_transition_mode[i]))

            else: # COMPATIBILITY: old logs (https://github.com/PX4/Firmware/pull/11918)
                vtol_states = cur_dataset.list_value_changes('in_transition_mode')
                vehicle_type_field = 'is_rotary_wing'
                vtol_state_mapping = {0: 2, 1: 3}
            for i in range(len(vtol_states)):
                if vtol_states[i][1] == 0:
                    t = vtol_states[i][0]
                    idx = np.argmax(cur_dataset.data['timestamp'] >= t) + 1
                    vtol_states[i] = (t, vtol_state_mapping[
                        cur_dataset.data[vehicle_type_field][idx]])
            vtol_states.append((ulog.last_timestamp, -1))
    except (KeyError, IndexError) as error:
        vtol_states = None



    # Heading
    curdoc().template_variables['title_html'] = get_heading_html(
        ulog, px4_ulog, db_data, link_to_3d_page,
        additional_links=[("Open PID Analysis", link_to_pid_analysis_page)])

    # info text on top (logging duration, max speed, ...)
    curdoc().template_variables['info_table_html'] = \
        get_info_table_html(ulog, px4_ulog, db_data, vehicle_data, vtol_states)

    curdoc().template_variables['error_labels_html'] = get_error_labels_html()

    hardfault_html = get_hardfault_html(ulog)
    if hardfault_html is not None:
        curdoc().template_variables['hardfault_html'] = hardfault_html

    corrupt_log_html = get_corrupt_log_html(ulog)
    if corrupt_log_html:
        curdoc().template_variables['corrupt_log_html'] = corrupt_log_html

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

    if any(elem.name == 'vehicle_gps_position' for elem in ulog.data_list):
        # Leaflet Map
        try:
            pos_datas, flight_modes = ulog_to_polyline(ulog, flight_mode_changes)
            curdoc().template_variables['pos_datas'] = pos_datas
            curdoc().template_variables['pos_flight_modes'] = flight_modes
        except:
            pass
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

    # Altitude estimate
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_axis_label='[m]', title='Altitude Estimate',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph([lambda data: ('alt', vehicle_gps_position_altitude)],
                        colors8[0:1], ['GPS Altitude (MSL)'])
    data_plot.change_dataset(baro_alt_meter_topic)
    data_plot.add_graph(['baro_alt_meter'], colors8[1:2], ['Barometer Altitude'])
    data_plot.change_dataset('vehicle_global_position')
    data_plot.add_graph(['alt'], colors8[2:3], ['Fused Altitude Estimation'])
    data_plot.change_dataset('position_setpoint_triplet')
    data_plot.add_circle(['current.alt'], [plot_config['mission_setpoint_color']],
                         ['Altitude Setpoint'])
    data_plot.change_dataset(actuator_controls_0.thrust_sp_topic)
    if actuator_controls_0.thrust_z_neg is not None:
        data_plot.add_graph([lambda data: ('thrust', actuator_controls_0.thrust_z_neg*100)],
                            colors8[6:7], ['Thrust [0, 100]'])
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

    if data_plot.finalize() is not None: plots.append(data_plot)

    # VTOL tailistter orientation conversion, if relevant
    if is_vtol_tailsitter:
        [tailsitter_attitude, tailsitter_rates, tailsitter_rates_setpoint] = tailsitter_orientation(
            ulog, vtol_states)

    # Roll/Pitch/Yaw angle & angular rate
    for index, axis in enumerate(['roll', 'pitch', 'yaw']):
        # angle
        axis_name = axis.capitalize()
        data_plot = DataPlot(data, plot_config, 'vehicle_attitude',
                             y_axis_label='[deg]', title=axis_name+' Angle',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        if is_vtol_tailsitter:
            if tailsitter_attitude[axis] is not None:
                data_plot.add_graph([lambda data: (axis+'_q',
                                                   np.rad2deg(tailsitter_attitude[axis]))],
                                    colors3[0:1], [axis_name+' Estimated'], mark_nan=True)
        else:
            data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                                colors3[0:1], [axis_name+' Estimated'], mark_nan=True)

        data_plot.change_dataset('vehicle_attitude_setpoint')
        data_plot.add_graph([lambda data: (axis+'_d', np.rad2deg(data[axis+'_d']))],
                            colors3[1:2], [axis_name+' Setpoint'],
                            use_step_lines=True)
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
        data_plot = DataPlot(data, plot_config, rate_estimated_topic_name,
                             y_axis_label='[deg/s]', title=axis_name+' Angular Rate',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        if is_vtol_tailsitter:
            if tailsitter_rates[axis] is not None:
                data_plot.add_graph([lambda data: (axis+'_q',
                                np.rad2deg(tailsitter_rates[axis]))],
                                colors3[0:1], [axis_name+' Rate Estimated'], mark_nan=True)
                data_plot.change_dataset('vehicle_rates_setpoint')
                data_plot.add_graph([lambda data: (axis, np.rad2deg(
                                tailsitter_rates_setpoint[axis]))],
                                colors3[1:2], [axis_name+' Rate Setpoint'],
                                mark_nan=True, use_step_lines=True)
        else:
            data_plot.add_graph([lambda data: (axis+'speed',
                                               np.rad2deg(data[rate_field_names[index]]))],
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
        data_plot.change_dataset(rate_groundtruth_topic_name)
        data_plot.add_graph([lambda data: (axis+'speed',
                                           np.rad2deg(data[rate_field_names[index]]))],
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
                            use_step_lines=True)
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

        if data_plot.finalize() is not None: plots.append(data_plot)

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

        data_plot.change_dataset(rate_groundtruth_topic_name)
        data_plot.add_graph([lambda data: ('rollspeed', np.rad2deg(data[rate_field_names[0]])),
                             lambda data: ('pitchspeed', np.rad2deg(data[rate_field_names[1]])),
                             lambda data: ('yawspeed', np.rad2deg(data[rate_field_names[2]]))],
                            colors8[2:5],
                            ['Roll Rate Groundtruth', 'Pitch Rate Groundtruth',
                             'Yaw Rate Groundtruth'])

        if data_plot.finalize() is not None: plots.append(data_plot)

        # Vision latency
        data_plot = DataPlot(data, plot_config, 'vehicle_visual_odometry',
                             y_axis_label='[ms]', title='Visual Odometry Latency',
                             plot_height='small', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(
            [lambda data: ('latency', 1e-3*(data['timestamp'] - data['timestamp_sample']))],
            colors3, ['VIO Latency'], mark_nan=True)
        plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

        if data_plot.finalize() is not None: plots.append(data_plot)

    # Airspeed vs Ground speed: but only if there's valid airspeed data or a VTOL
    try:
        if is_vtol or ulog.get_dataset('airspeed') is not None:
            data_plot = DataPlot(data, plot_config, 'vehicle_global_position',
                                 y_axis_label='[m/s]', title='Airspeed',
                                 plot_height='small',
                                 changed_params=changed_params, x_range=x_range)
            data_plot.add_graph([lambda data: ('groundspeed_estimated',
                                               np.sqrt(data['vel_n']**2 + data['vel_e']**2))],
                                colors8[0:1], ['Ground Speed Estimated'])
            if any(elem.name == 'airspeed_validated' for elem in data):
                airspeed_validated = ulog.get_dataset('airspeed_validated')
                data_plot.change_dataset('airspeed_validated')
                if np.amax(airspeed_validated.data['airspeed_sensor_measurement_valid']) == 1:
                    data_plot.add_graph(['true_airspeed_m_s'], colors8[1:2],
                                        ['True Airspeed'])
                else:
                    data_plot.add_graph(['true_ground_minus_wind_m_s'], colors8[1:2],
                                        ['True Airspeed (estimated)'])
            else:
                data_plot.change_dataset('airspeed')
                data_plot.add_graph(['indicated_airspeed_m_s'], colors8[1:2],
                                    ['Indicated Airspeed'])
            data_plot.change_dataset('vehicle_gps_position')
            data_plot.add_graph(['vel_m_s'], colors8[2:3], ['Ground Speed (from GPS)'])
            data_plot.change_dataset('tecs_status')
            data_plot.add_graph(['true_airspeed_sp'], colors8[3:4], ['True Airspeed Setpoint'])
            plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)

            if data_plot.finalize() is not None: plots.append(data_plot)
    except (KeyError, IndexError) as error:
        pass

    # TECS (fixed-wing or VTOLs)
    data_plot = DataPlot(data, plot_config, 'tecs_status', y_start=0, title='TECS',
                         y_axis_label='[m/s]', plot_height='small',
                         changed_params=changed_params, x_range=x_range)
    data_plot.add_graph(['height_rate', 'height_rate_setpoint'],
                        colors2, ['Height Rate', 'Height Rate Setpoint'],
                        mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)


    # manual control inputs
    # prefer the manual_control_setpoint topic. Old logs do not contain it
    if any(elem.name == 'manual_control_setpoint' for elem in data):
        data_plot = DataPlot(data, plot_config, 'manual_control_setpoint',
                             title='Manual Control Inputs (Radio or Joystick)',
                             plot_height='small', y_range=Range1d(-1.1, 1.1),
                             changed_params=changed_params, x_range=x_range)
        data_plot.add_graph(manual_control_sp_controls + ['aux1', 'aux2'], colors8[0:6],
                            ['Y / Roll', 'X / Pitch', 'Yaw',
                             'Throttle ' + manual_control_sp_throttle_range, 'Aux1', 'Aux2'])
        data_plot.change_dataset(manual_control_switches_topic)
        data_plot.add_graph([lambda data: ('mode_slot', data['mode_slot']/6),
                             lambda data: ('kill_switch', data['kill_switch'] == 1)],
                            colors8[6:8], ['Flight Mode', 'Kill Switch'])
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
            num_rc_channels = min(np.amax(data_plot.dataset.data['channel_count']), num_rc_channels)
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
    data_plot = DataPlot(data, plot_config, actuator_controls_0.torque_sp_topic,
                         y_start=0, title='Actuator Controls',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(actuator_controls_0.torque_axes_field_names,
                        colors8[0:3], ['Roll', 'Pitch', 'Yaw'], mark_nan=True)
    data_plot.change_dataset(actuator_controls_0.thrust_sp_topic)
    if actuator_controls_0.thrust_z_neg is not None:
        data_plot.add_graph([lambda data: ('thrust', actuator_controls_0.thrust_z_neg)],
                            colors8[3:4], ['Thrust (up)'], mark_nan=True)
    if actuator_controls_0.thrust_x is not None:
        data_plot.add_graph([lambda data: ('thrust', actuator_controls_0.thrust_x)],
                            colors8[4:5], ['Thrust (forward)'], mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)

    # actuator controls (Main) FFT (for filter & output noise analysis)
    data_plot = DataPlotFFT(data, plot_config, actuator_controls_0.torque_sp_topic,
                            title='Actuator Controls FFT', y_range = Range1d(0, 0.01))
    data_plot.add_graph(actuator_controls_0.torque_axes_field_names,
                        colors3, ['Roll', 'Pitch', 'Yaw'])
    if not data_plot.had_error:
        if 'MC_DTERM_CUTOFF' in ulog.initial_parameters: # COMPATIBILITY
            data_plot.mark_frequency(
                ulog.initial_parameters['MC_DTERM_CUTOFF'],
                'MC_DTERM_CUTOFF')
        if 'IMU_DGYRO_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['IMU_DGYRO_CUTOFF'],
                'IMU_DGYRO_CUTOFF')
        if 'IMU_GYRO_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['IMU_GYRO_CUTOFF'],
                'IMU_GYRO_CUTOFF', 20)

    if data_plot.finalize() is not None: plots.append(data_plot)


    # angular_velocity FFT (for filter & output noise analysis)
    data_plot = DataPlotFFT(data, plot_config, 'vehicle_angular_velocity',
                            title='Angular Velocity FFT', y_range = Range1d(0, 0.01))
    data_plot.add_graph(['xyz[0]', 'xyz[1]', 'xyz[2]'],
                        colors3, ['Rollspeed', 'Pitchspeed', 'Yawspeed'])
    if not data_plot.had_error:
        if 'IMU_GYRO_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['IMU_GYRO_CUTOFF'],
                'IMU_GYRO_CUTOFF', 20)
        if 'IMU_GYRO_NF_FREQ' in ulog.initial_parameters:
            if  ulog.initial_parameters['IMU_GYRO_NF_FREQ'] > 0:
                data_plot.mark_frequency(
                    ulog.initial_parameters['IMU_GYRO_NF_FREQ'],
                    'IMU_GYRO_NF_FREQ', 70)

    if data_plot.finalize() is not None: plots.append(data_plot)


    # angular_acceleration FFT (for filter & output noise analysis)
    data_plot = DataPlotFFT(data, plot_config, 'vehicle_angular_acceleration',
                            title='Angular Acceleration FFT')
    data_plot.add_graph(['xyz[0]', 'xyz[1]', 'xyz[2]'],
                        colors3, ['Roll accel', 'Pitch accel', 'Yaw accel'])
    if not data_plot.had_error:
        if 'IMU_DGYRO_CUTOFF' in ulog.initial_parameters:
            data_plot.mark_frequency(
                ulog.initial_parameters['IMU_DGYRO_CUTOFF'],
                'IMU_DGYRO_CUTOFF')
        if 'IMU_GYRO_NF_FREQ' in ulog.initial_parameters:
            if  ulog.initial_parameters['IMU_GYRO_NF_FREQ'] > 0:
                data_plot.mark_frequency(
                    ulog.initial_parameters['IMU_GYRO_NF_FREQ'],
                    'IMU_GYRO_NF_FREQ', 70)

    if data_plot.finalize() is not None: plots.append(data_plot)

    # actuator controls 1 (torque + thrust)
    # (only present on VTOL, Fixed-wing config)
    data_plot = DataPlot(data, plot_config, actuator_controls_1.torque_sp_topic,
                         y_start=0, title='Actuator Controls 1 (VTOL in Fixed-Wing mode)',
                         plot_height='small', changed_params=changed_params, topic_instance=1,
                         x_range=x_range)
    data_plot.add_graph(actuator_controls_1.torque_axes_field_names,
                        colors8[0:3], ['Roll', 'Pitch', 'Yaw'], mark_nan=True)
    data_plot.change_dataset(actuator_controls_1.thrust_sp_topic,
                             actuator_controls_1.topic_instance)
    if actuator_controls_1.thrust_x is not None:
        data_plot.add_graph([lambda data: ('thrust', actuator_controls_1.thrust_x)],
                            colors8[3:4], ['Thrust (forward)'], mark_nan=True)
    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
    if data_plot.finalize() is not None: plots.append(data_plot)

    if dynamic_control_alloc:

        # actuator motors, actuator servos
        actuator_output_plots = [("actuator_motors", "Motor"), ("actuator_servos", "Servo")]
        for topic_name, plot_name in actuator_output_plots:

            data_plot = DataPlot(data, plot_config, topic_name,
                                 y_range=Range1d(-1, 1), title=plot_name+' Outputs',
                                 plot_height='small', changed_params=changed_params,
                                 x_range=x_range)
            num_actuator_outputs = 12
            if data_plot.dataset:
                for i in range(num_actuator_outputs):
                    try:
                        output_data = data_plot.dataset.data['control['+str(i)+']']
                    except KeyError:
                        num_actuator_outputs = i
                        break

                    if np.isnan(output_data).all():
                        num_actuator_outputs = i
                        break

                if num_actuator_outputs > 0:
                    data_plot.add_graph(['control['+str(i)+']'
                                         for i in range(num_actuator_outputs)],
                                        [colors8[i % 8] for i in range(num_actuator_outputs)],
                                        [plot_name+' '+str(i+1)
                                         for i in range(num_actuator_outputs)])
                    plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
                    if data_plot.finalize() is not None: plots.append(data_plot)

    else:

        actuator_output_plots = [(0, "Actuator Outputs (Main)"), (1, "Actuator Outputs (AUX)"),
                                 (2, "Actuator Outputs (EXTRA)")]
        for topic_instance, plot_name in actuator_output_plots:

            data_plot = DataPlot(data, plot_config, 'actuator_outputs',
                                 y_start=0, title=plot_name, plot_height='small',
                                 changed_params=changed_params, topic_instance=topic_instance,
                                 x_range=x_range)
            num_actuator_outputs = 16
            # only plot if at least one of the outputs is not constant
            all_constant = True
            if data_plot.dataset:
                num_actuator_outputs = min(np.amax(data_plot.dataset.data['noutputs']),
                                           num_actuator_outputs)

                for i in range(num_actuator_outputs):
                    output_data = data_plot.dataset.data['output['+str(i)+']']
                    if not np.all(output_data == output_data[0]):
                        all_constant = False

            if not all_constant:
                data_plot.add_graph(['output['+str(i)+']' for i in range(num_actuator_outputs)],
                                    [colors8[i % 8] for i in range(num_actuator_outputs)],
                                    ['Output '+str(i) for i in range(num_actuator_outputs)],
                                    mark_nan=True)
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

    # Vibration Metrics
    data_plot = DataPlot(data, plot_config, 'vehicle_imu_status',
                         title='Vibration Metrics',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range, y_start=0, topic_instance=0)
    data_plot.add_graph(['accel_vibration_metric'], colors8[0:1],
                         ['Accel 0 Vibration Level [m/s^2]'])

    data_plot.change_dataset('vehicle_imu_status', 1)
    data_plot.add_graph(['accel_vibration_metric'], colors8[1:2],
                            ['Accel 1 Vibration Level [m/s^2]'])

    data_plot.change_dataset('vehicle_imu_status', 2)
    data_plot.add_graph(['accel_vibration_metric'], colors8[2:3],
                            ['Accel 2 Vibration Level [m/s^2]'])

    data_plot.change_dataset('vehicle_imu_status', 3)
    data_plot.add_graph(['accel_vibration_metric'], colors8[3:4],
                            ['Accel 3 Vibration Level [rad/s]'])

    data_plot.add_horizontal_background_boxes(
        ['green', 'orange', 'red'], [4.905, 9.81])

    if data_plot.finalize() is not None: plots.append(data_plot)

    # Acceleration Spectrogram
    data_plot = DataPlotSpec(data, plot_config, 'sensor_combined',
                             y_axis_label='[Hz]', title='Acceleration Power Spectral Density',
                             plot_height='small', x_range=x_range)
    data_plot.add_graph(['accelerometer_m_s2[0]', 'accelerometer_m_s2[1]', 'accelerometer_m_s2[2]'],
                        ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # Filtered Gyro (angular velocity) Spectrogram
    data_plot = DataPlotSpec(data, plot_config, 'vehicle_angular_velocity',
                             y_axis_label='[Hz]', title='Angular velocity Power Spectral Density',
                             plot_height='small', x_range=x_range)
    data_plot.add_graph(['xyz[0]', 'xyz[1]', 'xyz[2]'],
                        ['rollspeed', 'pitchspeed', 'yawspeed'])

    if data_plot.finalize() is not None: plots.append(data_plot)


    # Filtered angular acceleration Spectrogram
    data_plot = DataPlotSpec(data, plot_config, 'vehicle_angular_acceleration',
                             y_axis_label='[Hz]',
                             title='Angular acceleration Power Spectral Density',
                             plot_height='small', x_range=x_range)
    data_plot.add_graph(['xyz[0]', 'xyz[1]', 'xyz[2]'],
                        ['roll accel', 'pitch accel', 'yaw accel'])

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

    # FIFO accel
    for instance in range(3):
        if add_virtual_fifo_topic_data(ulog, 'sensor_accel_fifo', instance):
            # Raw data
            data_plot = DataPlot(data, plot_config, 'sensor_accel_fifo_virtual',
                                 y_axis_label='[m/s^2]',
                                 title=f'Raw Acceleration (FIFO, IMU{instance})',
                                 plot_height='small', changed_params=changed_params,
                                 x_range=x_range, topic_instance=instance)
            data_plot.add_graph(['x', 'y', 'z'], colors3, ['X', 'Y', 'Z'])
            if data_plot.finalize() is not None: plots.append(data_plot)

            # power spectral density
            data_plot = DataPlotSpec(data, plot_config, 'sensor_accel_fifo_virtual',
                                     y_axis_label='[Hz]',
                                     title=(f'Acceleration Power Spectral Density'
                                            f'(FIFO, IMU{instance})'),
                                     plot_height='normal', x_range=x_range, topic_instance=instance)
            data_plot.add_graph(['x', 'y', 'z'], ['X', 'Y', 'Z'])
            if data_plot.finalize() is not None: plots.append(data_plot)

            # sampling regularity
            data_plot = DataPlot(data, plot_config, 'sensor_accel_fifo', y_range=Range1d(0, 25e3),
                                 y_axis_label='[us]',
                                 title=f'Sampling Regularity of Sensor Data (FIFO, IMU{instance})',
                                 plot_height='small',
                                 changed_params=changed_params,
                                 x_range=x_range, topic_instance=instance)
            sensor_accel_fifo = ulog.get_dataset('sensor_accel_fifo').data
            sampling_diff = np.diff(sensor_accel_fifo['timestamp'])
            min_sampling_diff = np.amin(sampling_diff)
            plot_dropouts(data_plot.bokeh_plot, ulog.dropouts, min_sampling_diff)
            data_plot.add_graph([lambda data: ('timediff', np.append(sampling_diff, 0))],
                                [colors3[2]], ['delta t (between 2 logged samples)'])
            if data_plot.finalize() is not None: plots.append(data_plot)

    # FIFO gyro
    for instance in range(3):
        if add_virtual_fifo_topic_data(ulog, 'sensor_gyro_fifo', instance):
            # Raw data
            data_plot = DataPlot(data, plot_config, 'sensor_gyro_fifo_virtual',
                                 y_axis_label='[deg/s]', title=f'Raw Gyro (FIFO, IMU{instance})',
                                 plot_height='small', changed_params=changed_params,
                                 x_range=x_range, topic_instance=instance)
            data_plot.add_graph(['x', 'y', 'z'], colors3, ['X', 'Y', 'Z'])
            data_plot.add_graph([
                lambda data: ('x', np.rad2deg(data['x'])),
                lambda data: ('y', np.rad2deg(data['y'])),
                lambda data: ('z', np.rad2deg(data['z']))],
                                colors3, ['X', 'Y', 'Z'])
            if data_plot.finalize() is not None: plots.append(data_plot)

            # power spectral density
            data_plot = DataPlotSpec(data, plot_config, 'sensor_gyro_fifo_virtual',
                                     y_axis_label='[Hz]',
                                     title=f'Gyro Power Spectral Density (FIFO, IMU{instance})',
                                     plot_height='normal', x_range=x_range, topic_instance=instance)
            data_plot.add_graph(['x', 'y', 'z'], ['X', 'Y', 'Z'])
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
    data_plot.add_graph(['current_distance', 'variance'], colors3[0:2],
                        ['Distance', 'Variance'])

    # dist_bottom from estimator
    data_plot.change_dataset('vehicle_local_position')
    data_plot.add_graph(['dist_bottom', 'dist_bottom_valid'], colors8[2:4],
                            ['Estimated Distance Bottom [m]', 'Dist Bottom Valid'])
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
        colors3[0:1], ['Norm of Magnetic Field'])
    data_plot.change_dataset(actuator_controls_0.thrust_sp_topic)
    if actuator_controls_0.thrust is not None:
        data_plot.add_graph([lambda data: ('thrust', actuator_controls_0.thrust)],
                            colors3[1:2], ['Thrust'])
    if is_vtol and not dynamic_control_alloc:
        data_plot.change_dataset(actuator_controls_1.thrust_sp_topic)
        if actuator_controls_1.thrust_x is not None:
            data_plot.add_graph([lambda data: ('thrust', actuator_controls_1.thrust_x)],
                                colors3[2:3], ['Thrust (Fixed-wing'])
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
        if 'sensors3v3[0]' in data_plot.dataset.data and \
                        np.amax(data_plot.dataset.data['sensors3v3[0]']) > 0.0001:
            data_plot.add_graph(['sensors3v3[0]'], colors8[5:6], ['3.3 V'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    #Temperature
    data_plot = DataPlot(data, plot_config, 'sensor_baro',
                         y_start=0, y_axis_label='[C]', title='Temperature',
                         plot_height='small', changed_params=changed_params,
                         x_range=x_range)
    data_plot.add_graph(['temperature'], colors8[0:1],
                        ['Baro temperature'])
    data_plot.change_dataset('sensor_accel')
    data_plot.add_graph(['temperature'], colors8[2:3],
                        ['Accel temperature'])
    data_plot.change_dataset('airspeed')
    data_plot.add_graph(['air_temperature_celsius'], colors8[4:5],
                        ['Airspeed temperature'])
    data_plot.change_dataset('battery_status')
    data_plot.add_graph(['temperature'], colors8[6:7],
                        ['Battery temperature'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # estimator flags
    try:
        data_plot = DataPlot(data, plot_config, 'estimator_status',
                             y_start=0, title='Estimator Flags',
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


    # Failsafe flags
    try:
        data_plot = DataPlot(data, plot_config, 'vehicle_status',
                             y_start=0, title='Failsafe Flags',
                             plot_height='normal', changed_params=changed_params,
                             x_range=x_range)
        data_plot.add_graph(['failsafe', 'failsafe_and_user_took_over'], [colors8[0], colors8[1]],
                            ['In Failsafe', 'User Took Over'])
        num_graphs = 2
        skip_if_always_set = ['auto_mission_missing', 'offboard_control_signal_lost']

        data_plot.change_dataset('failsafe_flags')
        if data_plot.dataset is not None:
            failsafe_flags = data_plot.dataset.data
            for failsafe_field in failsafe_flags:
                if failsafe_field == 'timestamp' or failsafe_field.startswith('mode_req_'):
                    continue
                cur_data = failsafe_flags[failsafe_field]
                # filter: show only the flags that are set at some point
                if np.amax(cur_data) >= 1:
                    if failsafe_field in skip_if_always_set and np.amin(cur_data) >= 1:
                        continue
                    data_plot.add_graph([failsafe_field], [colors8[num_graphs % 8]],
                                        [failsafe_field.replace('_', ' ')])
                    num_graphs += 1
            plot_flight_modes_background(data_plot, flight_mode_changes, vtol_states)
            if data_plot.finalize() is not None: plots.append(data_plot)
    except (KeyError, IndexError) as error:
        print('Error in failsafe plot: '+str(error))


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


    user_agent = curdoc().session_context.request.headers.get("User-Agent", "")
    is_mobile = re.search(r'Mobile|iP(hone|od|ad)|Android|BlackBerry|'
            r'IEMobile|Kindle|NetFront|Silk-Accelerated|(hpw|web)OS|Fennec|'
            r'Minimo|Opera M(obi|ini)|Blazer|Dolfin|'
            r'Dolphin|Skyfire|Zune', user_agent)

    jinja_plot_data = []
    for i in range(len(plots)):
        if plots[i] is None:
            plots[i] = column(param_changes_button, width=int(plot_width * 0.99))
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
        if is_mobile is not None and hasattr(plots[i], 'toolbar'):
            # Disable panning on mobile by default
            plots[i].toolbar.active_drag = None


    # changed parameters
    plots.append(get_changed_parameters(ulog, plot_width))



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
#    plots.append(column(topics_div, width=int(plot_width*0.9)))


    # log messages
    plots.append(get_logged_messages(ulog, plot_width))


    # console messages, perf & top output
    top_data = ''
    perf_data = ''
    console_messages = ''
    if 'boot_console_output' in ulog.msg_info_multiple_dict:
        console_output = ulog.msg_info_multiple_dict['boot_console_output'][0]
        console_output = escape(''.join(console_output))
        console_messages = '<p><pre>'+console_output+'</pre></p>'

    for state in ['pre', 'post']:
        if 'perf_top_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_top_data = ulog.msg_info_multiple_dict['perf_top_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_top_data))
            top_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'
        if 'perf_counter_'+state+'flight' in ulog.msg_info_multiple_dict:
            current_perf_data = ulog.msg_info_multiple_dict['perf_counter_'+state+'flight'][0]
            flight_data = escape('\n'.join(current_perf_data))
            perf_data += '<p>'+state.capitalize()+' Flight:<br/><pre>'+flight_data+'</pre></p>'
    if 'perf_top_watchdog' in ulog.msg_info_multiple_dict:
        current_top_data = ulog.msg_info_multiple_dict['perf_top_watchdog'][0]
        flight_data = escape('\n'.join(current_top_data))
        top_data += '<p>Watchdog:<br/><pre>'+flight_data+'</pre></p>'

    additional_data_html = ''
    if len(console_messages) > 0:
        additional_data_html += '<h5>Console Output</h5>'+console_messages
    if len(top_data) > 0:
        additional_data_html += '<h5>Processes</h5>'+top_data
    if len(perf_data) > 0:
        additional_data_html += '<h5>Performance Counters</h5>'+perf_data
    if len(additional_data_html) > 0:
        # hide by default & use a button to expand
        additional_data_html = '''
<button id="show-additional-data-btn" class="btn btn-secondary" data-toggle="collapse" style="min-width:0;"
 data-target="#show-additional-data">Show additional Data</button>
<div id="show-additional-data" class="collapse">
{:}
</div>
'''.format(additional_data_html)
        curdoc().template_variables['additional_info'] = additional_data_html


    curdoc().template_variables['plots'] = jinja_plot_data

    return plots
