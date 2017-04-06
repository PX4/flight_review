""" This contains the list of all drawn plots on the log plotting page """

import cgi # for html escaping

from bokeh.layouts import widgetbox
from bokeh.models import ColumnDataSource, Range1d
from bokeh.models.widgets import DataTable, TableColumn, Div, Button
from bokeh.io import curdoc

from helper import *
from config import *
from plotting import *

#pylint: disable=deprecated-method, cell-var-from-loop, undefined-loop-variable,
#pylint: disable=redefined-variable-type, consider-using-enumerate


def generate_plots(ulog, px4_ulog, flight_mode_changes, db_data, vehicle_data):
    """ create a list of bokeh plots (and widgets) to show """

    plots = []
    data = ulog.data_list

    # Heading
    sys_name = ''
    if 'sys_name' in ulog.msg_info_dict:
        sys_name = cgi.escape(ulog.msg_info_dict['sys_name']) + ' '
    div = Div(text="<h1>"+sys_name + px4_ulog.get_mav_type()+"</h1>", width=int(plot_width*0.9))
    header_divs = [div]
    if db_data.description != '':
        div_descr = Div(text="<h4>"+db_data.description+"</h4>", width=int(plot_width*0.9))
        header_divs.append(div_descr)

    # airframe
    table_text = []
    if 'SYS_AUTOSTART' in ulog.initial_parameters:
        sys_autostart = ulog.initial_parameters['SYS_AUTOSTART']
        airframe_data = get_airframe_data(sys_autostart)

        if airframe_data is None:
            table_text.append(('Airframe', str(sys_autostart)))
        else:
            airframe_type = ''
            if 'type' in airframe_data:
                airframe_type = ', '+airframe_data['type']
            table_text.append(('Airframe', airframe_data.get('name')+
                               airframe_type+' <small>('+str(sys_autostart)+')</small>'))

    # HW & SW
    sys_hardware = ''
    if 'ver_hw' in ulog.msg_info_dict:
        sys_hardware = cgi.escape(ulog.msg_info_dict['ver_hw'])
        table_text.append(('Hardware', sys_hardware))

    release_str = ulog.get_version_info_str()
    if release_str is None:
        release_str = ''
        release_str_suffix = ''
    else:
        release_str += ' <small>('
        release_str_suffix = ')</small>'
    if 'ver_sw' in ulog.msg_info_dict:
        ver_sw = cgi.escape(ulog.msg_info_dict['ver_sw'])
        ver_sw_link = 'https://github.com/PX4/Firmware/commit/'+ver_sw
        table_text.append(('Software Version', release_str +
                           '<a href="'+ver_sw_link+'" target="_blank">'+ver_sw[:8]+'</a>'+
                           release_str_suffix))

    if 'sys_os_name' in ulog.msg_info_dict and 'sys_os_ver_release' in ulog.msg_info_dict:
        os_name = cgi.escape(ulog.msg_info_dict['sys_os_name'])
        os_ver = ulog.get_version_info_str('sys_os_ver_release')
        if os_ver is not None:
            table_text.append(('OS Version', os_name + ', ' + os_ver))

    table_text.append(('Estimator', px4_ulog.get_estimator()))

    # logging start time & date
    try:
        # get the first non-zero timestamp
        gps_data = ulog.get_dataset('vehicle_gps_position')
        indices = np.nonzero(gps_data.data['time_utc_usec'])
        if len(indices[0]) > 0:
            # we use the timestamp from the log and then convert it with JS to
            # display with local timezone
            logging_start_time = int(gps_data.data['time_utc_usec'][indices[0][0]] / 1000000)
            js_code = """
<script type="text/javascript">
    var logging_span = $('#logging-start-element');
    var d = new Date(0);
    d.setUTCSeconds(logging_span.text());
    var date_str = ("0" + d.getDate()).slice(-2) + "-" +
                   ("0"+(d.getMonth()+1)).slice(-2) + "-" + d.getFullYear() + " " +
                   ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
    logging_span.text(date_str);
    logging_span.show();
</script>
"""
            table_text.append(('Logging Start',
                               '<span style="display:none" id="logging-start-element">'+
                               str(logging_start_time)+'</span>'+js_code))
    except:
        # Ignore. Eg. if topic not found
        pass


    # logging duration
    m, s = divmod(int((ulog.last_timestamp - ulog.start_timestamp)/1e6), 60)
    h, m = divmod(m, 60)
    table_text.append(('Logging Duration', '{:d}:{:02d}:{:02d}'.format(h, m, s)))

    # dropouts
    dropout_durations = [dropout.duration for dropout in ulog.dropouts]
    if len(dropout_durations) > 0:
        total_duration = sum(dropout_durations) / 1000
        if total_duration > 5:
            total_duration_str = '{:.0f}'.format(total_duration)
        else:
            total_duration_str = '{:.2f}'.format(total_duration)
        table_text.append(('Dropouts', '{:} ({:} s)'.format(
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
        table_text.append(('Vehicle Flight Time', flight_time_str))

    # vehicle UUID (and name if provided). SITL does not have a UUID
    if 'sys_uuid' in ulog.msg_info_dict and sys_hardware != 'SITL':
        sys_uuid = cgi.escape(ulog.msg_info_dict['sys_uuid'])
        if vehicle_data is not None and vehicle_data.name != '':
            sys_uuid = sys_uuid + ' (' + vehicle_data.name + ')'
        if len(sys_uuid) > 0:
            table_text.append(('Vehicle UUID', sys_uuid))


    # Wind speed, rating, feedback
    if db_data.wind_speed >= 0:
        table_text.append(('Wind Speed', db_data.wind_speed_str()))
    if len(db_data.rating) > 0:
        table_text.append(('Flight Rating', db_data.rating_str()))
    if len(db_data.feedback) > 0:
        table_text.append(('Feedback', db_data.feedback.replace('\n', '<br/>')))
    if len(db_data.video_url) > 0:
        table_text.append(('Video', '<a href="'+db_data.video_url+
                           '" target="_blank">'+db_data.video_url+'</a>'))

    # generate the table
    divs_text = '<table>' + ''.join(
        ['<tr><td class="left">'+a+
         ':</td><td>'+b+'</td></tr>' for a, b in table_text]) + '</table>'
    header_divs.append(Div(text=divs_text, width=int(plot_width*0.9)))
    plots.append(widgetbox(header_divs, width=int(plot_width*0.9)))



# FIXME: for now, we use Google maps directly without bokeh, because it's not working reliably
    # GPS map
#    gps_plots = []
#    gps_titles = []
#    plot = plot_map(ulog, plot_config, map_type='google', api_key =
#            get_google_maps_api_key(), setpoints=False)
#    plot = None
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
#        x_axis_label = '[m]', y_axis_label='[m]', plot_height='gps_map')
#    data_plot.add_graph('y', 'x', colors2[0], 'Estimated')
#    data_plot.change_dataset('vehicle_local_position_setpoint')
#    data_plot.add_graph('y', 'x', colors2[1], 'Setpoint')
#    if data_plot.finalize() is not None:
#        gps_plots.append(data_plot.bokeh_plot)
#        gps_titles.append('Local Position')
#
#
#    if len(gps_plots) >= 2:
#        tabs = []
#        for i in range(len(gps_plots)):
#            tabs.append(Panel(child=gps_plots[i], title=gps_titles[i]))
#        gps_plot_height=plot_config['plot_height']['gps_map'] + 30
#        plots.append(Tabs(tabs=tabs, width=plot_width, height=gps_plot_height))
#    elif len(gps_plots) == 1:
#        plots.extend(gps_plots)


    # Position plot
    data_plot = DataPlot2D(data, plot_config, 'vehicle_local_position',
                           x_axis_label='[m]', y_axis_label='[m]', plot_height='gps_map')
    data_plot.add_graph('y', 'x', colors2[0], 'Estimated',
                        check_if_all_zero=True)
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
        curdoc().template_variables['has_position_data'] = True


    # initialize parameter changes
    changed_params = None
    if not 'replay' in ulog.msg_info_dict: # replay can have many param changes
        if len(ulog.changed_parameters) > 0:
            changed_params = ulog.changed_parameters
            plots.append(None) # save space for the param change button


    ### Add all data plots ###


    # Altitude estimate
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_axis_label='[m]', title='Altitude Estimate',
                         changed_params=changed_params)
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
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

    if data_plot.finalize() is not None: plots.append(data_plot)



    # Roll/Pitch/Yaw angle & angular rate
    for axis in ['roll', 'pitch', 'yaw']:

        # angle
        axis_name = axis.capitalize()
        data_plot = DataPlot(data, plot_config, 'vehicle_attitude',
                             y_axis_label='[deg]', title=axis_name+' Angle',
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            colors2[0:1], [axis_name+' Estimated'])
        data_plot.change_dataset('vehicle_attitude_setpoint')
        data_plot.add_graph([lambda data: (axis+'_d', np.rad2deg(data[axis+'_d']))],
                            colors2[1:2], [axis_name+' Setpoint'])
        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            [color_gray], [axis_name+' Groundtruth'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        if data_plot.finalize() is not None: plots.append(data_plot)

        # rate
        data_plot = DataPlot(data, plot_config, 'vehicle_attitude',
                             y_axis_label='[deg/s]', title=axis_name+' Angular Rate',
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph([lambda data: (axis+'speed', np.rad2deg(data[axis+'speed']))],
                            colors2[0:1], [axis_name+' Rate Estimated'])
        data_plot.change_dataset('vehicle_rates_setpoint')
        data_plot.add_graph([lambda data: (axis, np.rad2deg(data[axis]))],
                            colors2[1:2], [axis_name+' Rate Setpoint'])
        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: (axis+'speed', np.rad2deg(data[axis+'speed']))],
                            [color_gray], [axis_name+' Rate Groundtruth'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        if data_plot.finalize() is not None: plots.append(data_plot)



    # Local position
    for axis in ['x', 'y', 'z']:
        data_plot = DataPlot(data, plot_config, 'vehicle_local_position',
                             y_axis_label='[m]', title='Local Position '+axis.upper(),
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph([axis], colors2[0:1], [axis.upper()+' Estimated'])
        data_plot.change_dataset('vehicle_local_position_setpoint')
        data_plot.add_graph([axis], colors2[1:2], [axis.upper()+' Setpoint'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        if data_plot.finalize() is not None: plots.append(data_plot)



    # Velocity
    data_plot = DataPlot(data, plot_config, 'vehicle_local_position',
                         y_axis_label='[m/s]', title='Velocity',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['vx', 'vy', 'vz'], colors3, ['X', 'Y', 'Z'])
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

    if data_plot.finalize() is not None: plots.append(data_plot)


    # Vision position (only if topic found)
    if any(elem.name == 'vehicle_vision_position' for elem in data):
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_position',
                             y_axis_label='[m]', title='Vision Position',
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph(['x', 'y', 'z'], colors3, ['X', 'Y', 'Z'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['x', 'y', 'z'], colors8[2:5],
                            ['Groundtruth X', 'Groundtruth Y', 'Groundtruth Z'])

        if data_plot.finalize() is not None: plots.append(data_plot)


        # Vision velocity
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_position',
                             y_axis_label='[m]', title='Vision Velocity',
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph(['vx', 'vy', 'vz'], colors3, ['X', 'Y', 'Z'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        data_plot.change_dataset('vehicle_local_position_groundtruth')
        data_plot.add_graph(['vx', 'vy', 'vz'], colors8[2:5],
                            ['Groundtruth X', 'Groundtruth Y', 'Groundtruth Z'])
        if data_plot.finalize() is not None: plots.append(data_plot)


    # Vision attitude
    if any(elem.name == 'vehicle_vision_attitude' for elem in data):
        data_plot = DataPlot(data, plot_config, 'vehicle_vision_attitude',
                             y_axis_label='[deg]', title='Vision Attitude',
                             plot_height='small', changed_params=changed_params)
        data_plot.add_graph([lambda data: ('roll', np.rad2deg(data['roll'])),
                             lambda data: ('pitch', np.rad2deg(data['pitch'])),
                             lambda data: ('yaw', np.rad2deg(data['yaw']))],
                            colors3, ['Roll', 'Pitch', 'Yaw'])
        plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

        data_plot.change_dataset('vehicle_attitude_groundtruth')
        data_plot.add_graph([lambda data: ('roll', np.rad2deg(data['roll'])),
                             lambda data: ('pitch', np.rad2deg(data['pitch'])),
                             lambda data: ('yaw', np.rad2deg(data['yaw']))],
                            colors8[2:5],
                            ['Roll Groundtruth', 'Pitch Groundtruth', 'Yaw Groundtruth'])

        if data_plot.finalize() is not None: plots.append(data_plot)


    # Airspeed vs Ground speed
    try:
        control_state = ulog.get_dataset('control_state').data
        # only plot if valid airspeed
        if np.amax(control_state['airspeed_valid']) == 1:
            data_plot = DataPlot(data, plot_config, 'vehicle_global_position',
                                 y_axis_label='[m/s]', title='Airspeed',
                                 plot_height='small', changed_params=changed_params)
            data_plot.add_graph([lambda data: ('groundspeed_estimated',
                                               np.sqrt(data['vel_n']**2 + data['vel_e']**2))],
                                colors3[2:3], ['Ground Speed Estimated'])
            data_plot.change_dataset('control_state')
            data_plot.add_graph(['airspeed'], colors2[0:1], ['Airspeed Estimated'])

            plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

            if data_plot.finalize() is not None: plots.append(data_plot)
    except:
        pass



    # raw radio control inputs
    data_plot = DataPlot(data, plot_config, 'rc_channels',
                         title='Raw Radio Control Inputs',
                         plot_height='small', y_range=Range1d(-1.1, 1.1),
                         changed_params=changed_params)
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
                        colors8[0:num_rc_channels], legends)
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

    if data_plot.finalize() is not None: plots.append(data_plot)



    # actuator controls 0
    data_plot = DataPlot(data, plot_config, 'actuator_controls_0',
                         y_start=0, title='Actuator Controls 0', plot_height='small',
                         changed_params=changed_params)
    data_plot.add_graph(['control[0]', 'control[1]', 'control[2]', 'control[3]'],
                        colors8[0:4], ['Roll', 'Pitch', 'Yaw', 'Thrust'])
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)
    if data_plot.finalize() is not None: plots.append(data_plot)

    # actuator outputs
    data_plot = DataPlot(data, plot_config, 'actuator_outputs',
                         y_start=0, title='Actuator Outputs', plot_height='small',
                         changed_params=changed_params)
    num_actuator_outputs = 8
    if data_plot.dataset:
        max_outputs = np.amax(data_plot.dataset.data['noutputs'])
        if max_outputs < num_actuator_outputs: num_actuator_outputs = max_outputs
    data_plot.add_graph(['output['+str(i)+']' for i in
                         range(num_actuator_outputs)], colors8[0:num_actuator_outputs],
                        ['Output '+str(i) for i in range(num_actuator_outputs)])
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)

    if data_plot.finalize() is not None: plots.append(data_plot)



    # raw acceleration
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[m/s^2]', title='Raw Acceleration',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['accelerometer_m_s2[0]', 'accelerometer_m_s2[1]',
                         'accelerometer_m_s2[2]'], colors3, ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # raw angular speed
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[deg/s]', title='Raw Angular Speed (Gyroscope)',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph([
        lambda data: ('gyro_rad[0]', np.rad2deg(data['gyro_rad[0]'])),
        lambda data: ('gyro_rad[1]', np.rad2deg(data['gyro_rad[1]'])),
        lambda data: ('gyro_rad[2]', np.rad2deg(data['gyro_rad[2]']))],
                        colors3, ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # magnetic field strength
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='[gauss]', title='Raw Magnetic Field Strength',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['magnetometer_ga[0]', 'magnetometer_ga[1]',
                         'magnetometer_ga[2]'], colors3,
                        ['X', 'Y', 'Z'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # distance sensor
    data_plot = DataPlot(data, plot_config, 'distance_sensor',
                         y_start=0, y_axis_label='[m]', title='Distance Sensor',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['current_distance', 'covariance'], colors3[0:2],
                        ['Distance', 'Covariance'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # gps uncertainty
    # the accuracy values can be really large if there is no fix, so we limit the
    # y axis range to some sane values
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         title='GPS Uncertainty', y_range=Range1d(0, 40),
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['eph', 'epv', 'satellites_used', 'fix_type'], colors8[::2],
                        ['Horizontal position accuracy [m]', 'Vertical position accuracy [m]',
                         'Num Satellites used', 'GPS Fix'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # gps noise & jamming
    data_plot = DataPlot(data, plot_config, 'vehicle_gps_position',
                         y_start=0, title='GPS Noise & Jamming',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['noise_per_ms', 'jamming_indicator'], colors3[0:2],
                        ['Noise per ms', 'Jamming Indicator'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # thrust and magnetic field
    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_start=0, title='Thrust and Magnetic Field', plot_height='small',
                         changed_params=changed_params)
    data_plot.add_graph(
        [lambda data: ('len_mag', np.sqrt(data['magnetometer_ga[0]']**2 +
                                          data['magnetometer_ga[1]']**2 +
                                          data['magnetometer_ga[2]']**2))],
        colors2[0:1], ['Norm of Magnetic Field'])
    data_plot.change_dataset('actuator_controls_0')
    data_plot.add_graph([lambda data: ('thrust', data['control[3]'])],
                        colors2[1:2], ['Thrust'])
    if data_plot.finalize() is not None: plots.append(data_plot)


    # power
    # TODO: dischared in Ah?
    data_plot = DataPlot(data, plot_config, 'battery_status',
                         y_start=0, title='Power',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['voltage_v', 'voltage_filtered_v',
                         'current_a', lambda data: ('discharged_mah', data['discharged_mah']/100)],
                        colors8[::2],
                        ['Voltage  [V]', 'Voltage filtered [V]', 'Current [A]',
                         'Discharged Amount [mAh / 100]'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # estimator watchdog
    data_plot = DataPlot(data, plot_config, 'estimator_status',
                         y_start=0, title='Estimator Watchdog',
                         plot_height='small', changed_params=changed_params)
    data_plot.add_graph(['nan_flags', 'health_flags',
                         'timeout_flags'], colors3,
                        ['NaN Flags', 'Health Flags (vel, pos, hgt)',
                         'Timeout Flags (vel, pos, hgt)'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # RC Quality
    data_plot = DataPlot(data, plot_config, 'input_rc',
                         title='RC Quality', plot_height='small', y_range=Range1d(0, 1),
                         changed_params=changed_params)
    data_plot.add_graph([lambda data: ('rssi', data['rssi']/100), 'rc_lost'],
                        colors3[0:2], ['RSSI [0, 1]', 'RC Lost (Indicator)'])
    data_plot.change_dataset('vehicle_status')
    data_plot.add_graph(['rc_signal_lost'], colors3[2:3], ['RC Lost (Detected)'])
    if data_plot.finalize() is not None: plots.append(data_plot)



    # cpu load
    data_plot = DataPlot(data, plot_config, 'cpuload',
                         title='CPU & RAM', plot_height='small', y_range=Range1d(0, 1),
                         changed_params=changed_params)
    data_plot.add_graph(['ram_usage', 'load'], [colors3[1], colors3[2]],
                        ['RAM Usage', 'CPU Load'])
    data_plot.add_span('load', line_color=colors3[2])
    data_plot.add_span('ram_usage', line_color=colors3[1])
    plot_flight_modes_background(data_plot.bokeh_plot, flight_mode_changes)
    if data_plot.finalize() is not None: plots.append(data_plot)


    # sampling: time difference
    try:
        data_plot = DataPlot(data, plot_config, 'sensor_combined', y_start=0,
                             y_axis_label='[us]',
                             title='Sampling Regularity of Sensor Data', plot_height='small',
                             changed_params=changed_params)
        sensor_combined = ulog.get_dataset('sensor_combined').data
        sampling_diff = np.diff(sensor_combined['timestamp'])
        min_sampling_diff = np.amin(sampling_diff)

        plot_dropouts(data_plot.bokeh_plot, ulog.dropouts, min_sampling_diff)

        data_plot.add_graph([lambda data: ('timediff', np.append(sampling_diff, 0))],
                            [colors3[2]], ['delta t (between 2 samples)'])
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
            plots[i] = widgetbox(param_changes_button, width=int(plot_width*0.99))
        if isinstance(plots[i], DataPlot):
            if plots[i].param_change_label is not None:
                param_change_labels.append(plots[i].param_change_label)
            plots[i] = plots[i].bokeh_plot

            plot_title = plots[i].title.text
            fragment = 'Nav-'+plot_title.replace(' ', '-') \
                .replace('&', '_').replace('(', '').replace(')', '')
            jinja_plot_data.append({
                'model_id': plots[i].ref['id'],
                'fragment': fragment,
                'title': plot_title
                })


    # changed parameters
    param_names = []
    param_values = []
    param_defaults = []
    param_mins = []
    param_maxs = []
    param_descriptions = []
    default_params = get_default_parameters()
    for param_name in sorted(ulog.initial_parameters):
        param_value = ulog.initial_parameters[param_name]

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
    plots.append(widgetbox(div, data_table, width=plot_width))


    # log messages
    log_times = []
    log_levels = []
    log_messages = []
    for m in ulog.logged_messages:
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
    plots.append(widgetbox(div, data_table, width=plot_width))


    curdoc().template_variables['plots'] = jinja_plot_data

    return plots
