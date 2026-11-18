""" Closed loop response of the rate and attitude controllers, estimated from
the setpoint and the measured response in the frequency domain """

from dataclasses import dataclass

import numpy as np
from bokeh.models import DataRange1d, Range1d, Span

from config import colors3
from gyro_filter_analysis import DataPlotWithToggle, toggle_renderers

# segment length for the spectral estimate (at least, and at least 5 times the
# shown step response, otherwise slow responses are underestimated) and length of
# the shown step response
SEGMENT_S = 2.
SEGMENT_PER_STEP_RESPONSE = 2.5
RATE_STEP_RESPONSE_S = 1.
YAW_RATE_STEP_RESPONSE_S = 4.
ANGLE_STEP_RESPONSE_S = 3.
# a segment is used if the setpoint varies at least this much [deg/s or deg]
MIN_SETPOINT_STD = 5.
# the response is trusted where the coherence is above this
MIN_COHERENCE = 0.6
# the response of a single segment uses the average where the setpoint power is
# below about this fraction of its maximum
WINDOW_REGULARIZATION = 0.02


@dataclass
class ClosedLoopResponse:
    """ estimated closed loop response of one axis """
    frequencies: np.ndarray
    response: np.ndarray # complex frequency response setpoint -> measurement
    coherence: np.ndarray
    valid_max_hz: float # highest frequency with a trusted estimate
    step_time: np.ndarray # [s]
    step: np.ndarray
    num_segments: int
    window_steps: list # step response estimated from each segment alone

    def time_to_setpoint(self):
        """ :return: time [s] when the step response first reaches the setpoint
        (1), or 90 % of its final value if it stays below """
        final = self.metrics()['final']
        reached = np.flatnonzero(self.step >= min(1., 0.9 * final))
        return self.step_time[reached[0]] if len(reached) > 0 else self.step_time[-1]

    def metrics(self):
        """ :return: dict with rise time [ms], delay [ms] (to 50 %),
        overshoot [%], final value (mean over the last 40 %)"""
        final = float(np.mean(self.step[self.step_time >= 0.6 * self.step_time[-1]]))
        result = {'final': final}
        if final > 0.1:
            def crossing(level):
                index = np.flatnonzero(self.step >= level * final)
                return self.step_time[index[0]] * 1e3 if len(index) > 0 else np.nan
            result['rise_ms'] = crossing(0.9) - crossing(0.1)
            result['delay_ms'] = crossing(0.5)
            result['overshoot'] = max(0., (np.max(self.step) - final) / final * 100)
        return result


def _zero_order_hold(timestamps, values, new_timestamps):
    """ value of a setpoint (piecewise constant) at new_timestamps """
    index = np.searchsorted(timestamps, new_timestamps, side='right') - 1
    return values[np.clip(index, 0, len(values) - 1)]


def estimate_response(setpoint_time, setpoint, measured_time, measured, intervals=None,
                      step_response_s=RATE_STEP_RESPONSE_S):
    """ estimate the closed loop response from setpoint to measurement.

    Both signals are put on the time grid of the measurement (the setpoint is
    held between updates). The frequency response is the averaged cross
    spectrum divided by the averaged setpoint spectrum (H1 estimate) over all
    segments where the setpoint varies, which is robust against noise on the
    measurement. The step response is the integral of the impulse response,
    limited to the frequencies with a trusted estimate (coherence).

    :param setpoint_time, measured_time: timestamps [us]
    :param intervals: list of (start, end) timestamps to use, or None
    :return: ClosedLoopResponse or None if there is not enough excitation
    """
    dt_us = np.median(np.diff(measured_time))
    sample_rate = 1e6 / dt_us
    segment_s = max(SEGMENT_S, SEGMENT_PER_STEP_RESPONSE * step_response_s)
    nperseg = int(2 ** np.round(np.log2(segment_s * sample_rate)))
    setpoint_held = _zero_order_hold(setpoint_time, setpoint, measured_time)
    mask = np.ones(len(measured_time), dtype=bool)
    if intervals is not None:
        mask = np.zeros(len(measured_time), dtype=bool)
        for start, end in intervals:
            mask |= (measured_time >= start) & (measured_time <= end)
    # no logging gaps within a segment
    gaps = np.flatnonzero(np.diff(measured_time) > 3 * dt_us)

    window = np.hanning(nperseg)
    sum_uu = np.zeros(nperseg // 2 + 1)
    sum_yy = np.zeros(nperseg // 2 + 1)
    sum_uy = np.zeros(nperseg // 2 + 1, dtype=complex)
    num_segments = 0
    segment_spectra = []
    for start in range(0, len(setpoint_held) - nperseg, nperseg // 2):
        end = start + nperseg
        if not np.all(mask[start:end]) or np.any((gaps >= start) & (gaps < end - 1)):
            continue
        setpoint_segment = setpoint_held[start:end]
        if np.std(setpoint_segment) < MIN_SETPOINT_STD:
            continue
        measured_segment = measured[start:end]
        u_f = np.fft.rfft((setpoint_segment - np.mean(setpoint_segment)) * window)
        y_f = np.fft.rfft((measured_segment - np.mean(measured_segment)) * window)
        sum_uu += np.abs(u_f) ** 2
        sum_yy += np.abs(y_f) ** 2
        sum_uy += np.conj(u_f) * y_f
        segment_spectra.append((u_f, y_f))
        num_segments += 1
    if num_segments == 0:
        return None

    frequencies = np.fft.rfftfreq(nperseg, 1. / sample_rate)
    response = sum_uy / np.maximum(sum_uu, 1e-20)
    coherence = np.abs(sum_uy) ** 2 / np.maximum(sum_uu * sum_yy, 1e-20)
    response[0] = response[1] # the mean is removed, use the lowest frequency

    # trusted up to where the (smoothed) coherence drops
    smoothed = np.convolve(coherence, np.ones(5) / 5, mode='same')
    low = np.flatnonzero((frequencies > 0.5) & (smoothed < MIN_COHERENCE))
    valid_max_hz = float(frequencies[low[0]]) if len(low) > 0 else float(frequencies[-1])
    valid_max_hz = max(valid_max_hz, 5.)

    # step response: roll off the response above the trusted range
    taper = np.ones(len(frequencies))
    roll_off = (frequencies > valid_max_hz) & (frequencies < 2 * valid_max_hz)
    taper[roll_off] = 0.5 * (1 + np.cos(np.pi * (frequencies[roll_off] - valid_max_hz)
                                        / valid_max_hz))
    taper[frequencies >= 2 * valid_max_hz] = 0
    num_samples = min(int(step_response_s * sample_rate), nperseg)

    def to_step(frequency_response):
        return np.cumsum(np.fft.irfft(frequency_response * taper, nperseg)[:num_samples])

    # each segment alone: where the segment has little setpoint power (e.g. a
    # sine excites a single frequency), its estimate falls back to the average
    window_steps = []
    for u_f, y_f in segment_spectra:
        power = np.abs(u_f) ** 2
        weight = WINDOW_REGULARIZATION * np.max(power)
        window_response = (np.conj(u_f) * y_f + weight * response) / (power + weight)
        window_response[0] = window_response[1] # the mean is removed
        window_steps.append(to_step(window_response))
    return ClosedLoopResponse(frequencies, response, coherence, valid_max_hz,
                              np.arange(num_samples) / sample_rate, to_step(response),
                              num_segments, window_steps)


def _metrics_label(name, metrics):
    if 'rise_ms' not in metrics:
        return f'{name}: no response'
    return (f"{name}: delay {metrics['delay_ms']:.0f} ms, rise {metrics['rise_ms']:.0f} ms, "
            f"overshoot {metrics['overshoot']:.0f}%")


def _style_legend(p, location):
    p.legend.location = location
    p.legend.label_text_font_size = '8pt'
    p.legend.click_policy = 'hide'
    p.legend.background_fill_alpha = 0.7


class DataPlotStepResponse(DataPlotWithToggle):
    """ estimated step response of the closed loop: the average over the
    flight, and optionally the estimate from each window alone """

    def __init__(self, data, config, title):
        super().__init__(data, config, 'vehicle_angular_velocity', x_axis_label='Time [ms]',
                         y_axis_label='Response', title=title, plot_height='normal')
        self._use_time_formatter = False

    def add_graphs(self, responses):
        """ :param responses: list of (axis name, color, ClosedLoopResponse or None) """
        if self._had_error: return
        responses = [(name, color, response) for name, color, response in responses
                     if response is not None]
        if len(responses) == 0:
            self._had_error = True
            return
        p = self._p
        window_renderers = []
        for name, color, response in responses:
            time_ms = response.step_time * 1e3
            window_renderers.append(p.multi_line(
                [time_ms] * len(response.window_steps), response.window_steps,
                line_color=color, line_alpha=max(0.05, min(0.4, 3. / len(response.window_steps))),
                line_width=1, visible=False))
            p.line(time_ms, response.step, line_color=color, line_width=2.5,
                   legend_label=_metrics_label(name, response.metrics()))
        p.add_layout(Span(location=1, dimension='width', line_color='black',
                          line_dash='dashed', line_width=1))
        p.y_range = DataRange1d(only_visible=True)
        # four times the time to reach the setpoint
        step_length = max(response.step_time[-1] for _, _, response in responses)
        reached = max(response.time_to_setpoint() for _, _, response in responses)
        p.x_range = Range1d(0, 1e3 * min(step_length, max(4. * reached, 0.2)),
                            bounds=(0, step_length * 1e3))
        _style_legend(p, 'bottom_right')
        self._toggles.append(toggle_renderers(['Average', 'Average and every window'],
                                              [[], window_renderers]))


def get_rate_responses(ulog, intervals):
    """ :return: list of (axis name, color, ClosedLoopResponse or None) for roll,
    pitch and yaw rate, or None if the data is missing """
    try:
        rates = ulog.get_dataset('vehicle_angular_velocity')
        rates_sp = ulog.get_dataset('vehicle_rates_setpoint')
    except (KeyError, IndexError, ValueError):
        return None
    rate_time = rates.data['timestamp_sample'] if 'timestamp_sample' in rates.data \
        else rates.data['timestamp']
    return [(axis.capitalize(), colors3[index], estimate_response(
        rates_sp.data['timestamp'], np.rad2deg(rates_sp.data[axis]),
        rate_time, np.rad2deg(rates.data[f'xyz[{index}]']), intervals,
        YAW_RATE_STEP_RESPONSE_S if axis == 'yaw' else RATE_STEP_RESPONSE_S))
            for index, axis in enumerate(['roll', 'pitch', 'yaw'])]


def get_angle_responses(ulog, intervals):
    """ :return: list of (axis name, color, ClosedLoopResponse or None) for roll
    and pitch angle, or None if the data is missing """
    try:
        attitude = ulog.get_dataset('vehicle_attitude')
        attitude_sp = ulog.get_dataset('vehicle_attitude_setpoint')
    except (KeyError, IndexError, ValueError):
        return None
    return [(axis.capitalize(), colors3[index], estimate_response(
        attitude_sp.data['timestamp'], _euler(attitude_sp.data, 'q_d', index),
        attitude.data['timestamp'], _euler(attitude.data, 'q', index),
        intervals, ANGLE_STEP_RESPONSE_S))
            for index, axis in enumerate(['roll', 'pitch'])]


def step_response_plot(ulog, plot_config, axis_response, label):
    """ :param axis_response: (axis name, color, ClosedLoopResponse or None)
    :param label: 'Rate' or 'Angle'
    :return: DataPlotStepResponse """
    data_plot = DataPlotStepResponse(ulog.data_list, plot_config,
                                     f'Step Response for {axis_response[0]} {label}')
    data_plot.add_graphs([axis_response])
    return data_plot


def _euler(data, field, index):
    """ roll (index 0) or pitch (index 1) in degrees from a quaternion field """
    quat = [data[f'{field}[{i}]'] for i in range(4)]
    if index == 0:
        angle = np.arctan2(2 * (quat[0] * quat[1] + quat[2] * quat[3]),
                           1 - 2 * (quat[1] * quat[1] + quat[2] * quat[2]))
    else:
        angle = np.arcsin(np.clip(2 * (quat[0] * quat[2] - quat[3] * quat[1]), -1, 1))
    return np.rad2deg(angle)
