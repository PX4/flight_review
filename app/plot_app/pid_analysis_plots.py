""" This contains PID analysis plots """
from bokeh.io import curdoc
from bokeh.models import DataRange1d, LinearAxis, Range1d
from bokeh.models.widgets import Div
from bokeh.layouts import column

from config import plot_width, plot_config, colors3
from helper import get_flight_mode_changes, ActuatorControls
from gyro_filter_analysis import get_flying_intervals
from rate_response import (
    get_angle_responses, get_rate_responses, step_response_plot
    )
from plotting import *
from plotted_tables import get_heading_html

#pylint: disable=cell-var-from-loop, undefined-loop-variable,

def get_pid_analysis_plots(ulog, px4_ulog, db_data, link_to_main_plots):
    """
    get all bokeh plots shown on the PID analysis page
    :return: list of bokeh plots
    """
    page_intro = """
<p>
This page shows how well the rate and attitude controllers follow their
setpoints, estimated from the setpoint and the measured rate (or angle) while
flying. The estimate needs excitation: stick inputs on every axis (quick rolls
and pitch changes, or a chirp) and the setpoint logged at the controller rate
(SDLOG_PROFILE bit 4 or 12). With only hovering, there is nothing to estimate.
</p>
<p>
<b>Step response</b>: how the vehicle would respond to an instant setpoint
change of 1. It is the average over all windows of the flight where the
setpoint varies; "every window" shows the estimate of each window alone (where
a window has no excitation at a frequency, it falls back to the average), so
the spread shows how consistent the response is.
</p>
<ul>
<li><b>Delay</b>: time until the response reaches 50 % of the step. It is the
sum of the filter delays, the motor spin-up and the controller.</li>
<li><b>Rise time</b>: time from 10 % to 90 % of the step. Higher P (or
feed forward) makes it shorter.</li>
<li><b>Overshoot</b>: how far the response goes beyond the setpoint, in %.
Small overshoot (up to 10-15 %) is normal, large overshoot or ringing means too
much P or too little D.</li>
</ul>
"""
    curdoc().template_variables['title_html'] = get_heading_html(
        ulog, px4_ulog, db_data, None, [('Open Main Plots', link_to_main_plots)],
        'PID Analysis') + page_intro

    plots = []
    data = ulog.data_list
    intervals = get_flying_intervals(ulog)
    rate_responses = get_rate_responses(ulog, intervals)
    num_responses = 0

    def add_response_plot(data_plot):
        nonlocal num_responses
        if data_plot.finalize() is not None:
            plots.append(data_plot.layout)
            num_responses += 1
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
    dynamic_control_alloc = any(elem.name in ('actuator_motors', 'actuator_servos')
                                for elem in data)
    actuator_controls_0 = ActuatorControls(ulog, dynamic_control_alloc, 0)

    for index, axis in enumerate(['roll', 'pitch', 'yaw']):
        axis_name = axis.capitalize()
        # rate
        data_plot = DataPlot(data, plot_config, actuator_controls_0.thrust_sp_topic,
                             y_axis_label='[deg/s]', title=axis_name+' Angular Rate',
                             plot_height='small',
                             x_range=x_range)

        thrust_sp_data = data_plot.dataset
        if thrust_sp_data is None: # do not show the rate plot if actuator_controls is missing
            continue
        time_thrust = thrust_sp_data.data['timestamp']
        thrust = actuator_controls_0.thrust * 100
        # downsample if necessary
        max_num_data_points = 4.0*plot_config['plot_width']
        if len(time_thrust) > max_num_data_points:
            step_size = int(len(time_thrust) / max_num_data_points)
            time_thrust = time_thrust[::step_size]
            thrust = thrust[::step_size]
        if len(time_thrust) > 0:
            # make sure the polygon reaches down to 0
            thrust = np.insert(thrust, [0, len(thrust)], [0, 0])
            time_thrust = np.insert(time_thrust, [0, len(time_thrust)],
                                      [time_thrust[0], time_thrust[-1]])

        # thrust on its own axis on the right
        p = data_plot.bokeh_plot
        p.extra_y_ranges = {'thrust': Range1d(0, 100)}
        p.add_layout(LinearAxis(y_range_name='thrust', axis_label='Thrust [%]'), 'right')
        thrust_patch = p.patch(time_thrust, thrust, line_width=0, fill_color='#555555', # pylint: disable=too-many-function-args
                               fill_alpha=0.25, alpha=0, legend_label='Thrust [%]',
                               y_range_name='thrust')

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
        # the rate axis range ignores the thrust
        p.y_range = DataRange1d(renderers=[r for r in p.renderers if r is not thrust_patch])

        if data_plot.finalize() is not None: plots.append(data_plot.bokeh_plot)

        # step response, estimated from the whole flight
        if rate_responses is not None:
            add_response_plot(step_response_plot(ulog, plot_config, rate_responses[index],
                                                 'Rate'))

    # attitude (yaw is mostly controlled directly by rate)
    for angle_response in get_angle_responses(ulog, intervals) or []:
        add_response_plot(step_response_plot(ulog, plot_config, angle_response, 'Angle'))

    if num_responses == 0:
        plots.insert(0, column(Div(
            text="<p><b>Error</b>: no controller response could be estimated: the "
            "setpoints vary too little (no stick inputs) or are logged at a too low "
            "rate.</p>", width=int(plot_width*0.9)), width=int(plot_width*0.9)))

    return plots
