""" This contains PID analysis plots """
from bokeh.io import curdoc
from bokeh.models.widgets import Div
from bokeh.layouts import column
from scipy.interpolate import interp1d

from config import plot_width, plot_config, colors3
from helper import get_flight_mode_changes
from pid_analysis import Trace, plot_pid_response
from plotting import *
from plotted_tables import get_heading_html

#pylint: disable=cell-var-from-loop, undefined-loop-variable,

def get_pid_analysis_plots(ulog, px4_ulog, db_data, link_to_main_plots):
    """
    get all bokeh plots shown on the PID analysis page
    :return: list of bokeh plots
    """
    def _resample(time_array, data, desired_time):
        """ resample data at a given time to a vector of desired_time """
        data_f = interp1d(time_array, data, fill_value='extrapolate')
        return data_f(desired_time)

    page_intro = """
<p>
This page shows step response plots for the PID controller. The step
response is an objective measure to evaluate the performance of a PID
controller, i.e. if the tuning gains are appropriate. In particular, the
following metrics can be read from the plots: response time, overshoot and
settling time.
</p>
<p>
The step response plots are based on <a href="https://github.com/Plasmatree/PID-Analyzer">
PID-Analyzer</a>, originally written for Betaflight by Florian Melsheimer.
Documentation with some examples can be found <a
href="https://github.com/Plasmatree/PID-Analyzer/wiki/Influence-of-parameters">here</a>.
</p>
<p>
The analysis may take a while...
</p>
    """
    curdoc().template_variables['title_html'] = get_heading_html(
        ulog, px4_ulog, db_data, None, [('Open Main Plots', link_to_main_plots)],
        'PID Analysis') + page_intro

    plots = []
    data = ulog.data_list
    flight_mode_changes = get_flight_mode_changes(ulog)
    x_range_offset = (ulog.last_timestamp - ulog.start_timestamp) * 0.05
    x_range = Range1d(ulog.start_timestamp - x_range_offset, ulog.last_timestamp + x_range_offset)

    # COMPATIBILITY support for old logs
    if any(elem.name == 'vehicle_angular_velocity' for elem in data):
        rate_topic_name = 'vehicle_angular_velocity'
        rate_field_names = ['xyz[0]', 'xyz[1]', 'xyz[2]']
    else: # old
        rate_topic_name = 'rate_ctrl_status'
        rate_field_names = ['rollspeed', 'pitchspeed', 'yawspeed']

    # required PID response data
    pid_analysis_error = False
    try:
        # Rate
        rate_data = ulog.get_dataset(rate_topic_name)
        gyro_time = rate_data.data['timestamp']

        vehicle_rates_setpoint = ulog.get_dataset('vehicle_rates_setpoint')
        actuator_controls_0 = ulog.get_dataset('actuator_controls_0')
        throttle = _resample(actuator_controls_0.data['timestamp'],
                             actuator_controls_0.data['control[3]'] * 100, gyro_time)
        time_seconds = gyro_time / 1e6
    except (KeyError, IndexError, ValueError) as error:
        print(type(error), ":", error)
        pid_analysis_error = True
        div = Div(text="<p><b>Error</b>: missing topics or data for PID analysis "
                  "(required topics: vehicle_angular_velocity, vehicle_rates_setpoint, "
                  "vehicle_attitude, vehicle_attitude_setpoint and "
                  "actuator_controls_0).</p>", width=int(plot_width*0.9))
        plots.append(column(div, width=int(plot_width*0.9)))

    has_attitude = True
    try:
        # Attitude (optional)
        vehicle_attitude = ulog.get_dataset('vehicle_attitude')
        attitude_time = vehicle_attitude.data['timestamp']
        vehicle_attitude_setpoint = ulog.get_dataset('vehicle_attitude_setpoint')
    except (KeyError, IndexError, ValueError) as error:
        print(type(error), ":", error)
        has_attitude = False

    for index, axis in enumerate(['roll', 'pitch', 'yaw']):
        axis_name = axis.capitalize()
        # rate
        data_plot = DataPlot(data, plot_config, 'actuator_controls_0',
                             y_axis_label='[deg/s]', title=axis_name+' Angular Rate',
                             plot_height='small',
                             x_range=x_range)

        thrust_max = 200
        actuator_controls = data_plot.dataset
        if actuator_controls is None: # do not show the rate plot if actuator_controls is missing
            continue
        time_controls = actuator_controls.data['timestamp']
        thrust = actuator_controls.data['control[3]'] * thrust_max
        # downsample if necessary
        max_num_data_points = 4.0*plot_config['plot_width']
        if len(time_controls) > max_num_data_points:
            step_size = int(len(time_controls) / max_num_data_points)
            time_controls = time_controls[::step_size]
            thrust = thrust[::step_size]
        if len(time_controls) > 0:
            # make sure the polygon reaches down to 0
            thrust = np.insert(thrust, [0, len(thrust)], [0, 0])
            time_controls = np.insert(time_controls, [0, len(time_controls)],
                                      [time_controls[0], time_controls[-1]])

        p = data_plot.bokeh_plot
        p.patch(time_controls, thrust, line_width=0, fill_color='#555555', # pylint: disable=too-many-function-args
                fill_alpha=0.4, alpha=0, legend_label='Thrust [0, {:}]'.format(thrust_max))

        data_plot.change_dataset(rate_topic_name)
        data_plot.add_graph([lambda data: ("rate"+str(index),
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
        plot_flight_modes_background(data_plot, flight_mode_changes)

        if data_plot.finalize() is not None: plots.append(data_plot.bokeh_plot)

        # PID response
        if not pid_analysis_error:
            try:
                gyro_rate = np.rad2deg(rate_data.data[rate_field_names[index]])
                setpoint = _resample(vehicle_rates_setpoint.data['timestamp'],
                                     np.rad2deg(vehicle_rates_setpoint.data[axis]),
                                     gyro_time)
                trace = Trace(axis, time_seconds, gyro_rate, setpoint, throttle)
                plots.append(plot_pid_response(trace, ulog.data_list, plot_config).bokeh_plot)
            except Exception as e:
                print(type(e), axis, ":", e)
                div = Div(text="<p><b>Error</b>: PID analysis failed. Possible "
                          "error causes are: logged data rate is too low, or there "
                          "is not enough motion for the analysis.</p>",
                          width=int(plot_width*0.9))
                plots.insert(0, column(div, width=int(plot_width*0.9)))
                pid_analysis_error = True

    # attitude
    if not pid_analysis_error and has_attitude:
        throttle = _resample(actuator_controls_0.data['timestamp'],
                             actuator_controls_0.data['control[3]'] * 100, attitude_time)
        time_seconds = attitude_time / 1e6
    # don't plot yaw, as yaw is mostly controlled directly by rate
    for index, axis in enumerate(['roll', 'pitch']):
        axis_name = axis.capitalize()

        # PID response
        if not pid_analysis_error and has_attitude:
            try:
                attitude_estimated = np.rad2deg(vehicle_attitude.data[axis])
                setpoint = _resample(vehicle_attitude_setpoint.data['timestamp'],
                                     np.rad2deg(vehicle_attitude_setpoint.data[axis+'_d']),
                                     attitude_time)
                trace = Trace(axis, time_seconds, attitude_estimated, setpoint, throttle)
                plots.append(plot_pid_response(trace, ulog.data_list, plot_config,
                                               'Angle').bokeh_plot)
            except Exception as e:
                print(type(e), axis, ":", e)
                div = Div(text="<p><b>Error</b>: Attitude PID analysis failed. Possible "
                          "error causes are: logged data rate is too low/data missing, "
                          "or there is not enough motion for the analysis.</p>",
                          width=int(plot_width*0.9))
                plots.insert(0, column(div, width=int(plot_width*0.9)))
                pid_analysis_error = True

    return plots
