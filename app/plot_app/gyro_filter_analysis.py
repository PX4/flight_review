""" Gyro filter analysis: gyro spectra before and after filtering, the
tracking of the dynamic notch filters (ESC RPM and FFT), the filter delay and
the noise over throttle """

from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import scipy.signal
from bokeh.layouts import column, row
from bokeh.models import (
    BasicTicker, BoxZoomTool, ColorBar, CustomJS, Label, Legend, LegendItem,
    LinearColorMapper, PanTool, PrintfTickFormatter, RadioButtonGroup, Range1d, ResetTool,
    SaveTool, Span, WheelZoomTool
    )

from config import debug_verbose_output
from plotting import DataPlot, add_virtual_fifo_topic_data

# ESC RPM notch harmonics and FFT notch peaks. The spectrogram colors stand out
# against the Viridis colormap, the PSD colors against a white background.
ESC_HARMONIC_SPEC_COLORS = ['#ff2020', '#ff9020', '#ff60e0', '#ffffff', '#ffb0b0', '#c0c0c0',
                            '#ffd8a0']
ESC_HARMONIC_PSD_COLORS = ['#d55e00', '#e69f00', '#cc79a7', '#0072b2', '#009e73', '#56b4e9',
                           '#f0e442']
FFT_PEAK_SPEC_COLORS = ['#ffffff', '#c0f0ff', '#a0ffa0']
MOTOR_SPEC_COLORS = ['#ff2020', '#ffffff', '#ff60e0', '#ffb000', '#00e0ff', '#a0ff60', '#c080ff',
                     '#ffff80']
FFT_PEAK_PSD_COLORS = ['#555555', '#009e73', '#56b4e9']

AXES = ['x', 'y', 'z']
AXIS_NAMES = ['X (Roll)', 'Y (Pitch)', 'Z (Yaw)']

# PX4 vehicle_status.arming_state
ARMING_STATE_ARMED = 2

# missing throttle bins up to this many are interpolated in the noise over throttle
MAX_THROTTLE_GAP_BINS = 2

# the filter delay is given as phase delay at this frequency (around the rate
# controller crossover, where the delay costs phase margin)
DELAY_FREQUENCY_HZ = 20.


@dataclass
class NotchTrack:
    """ frequency of a group of notch filters over time: one ESC RPM harmonic
    of all motors, or one FFT peak of all axes """
    name: str
    kind: str # 'esc' or 'fft'
    index: int # harmonic or peak (0 = first)
    segments: list # list of (timestamps [us], frequencies [Hz] (NaN = disabled), axis or None)
    bandwidth_hz: float
    segment_names: list = field(default_factory=list) # e.g. 'Motor 1' per segment

    def valid_frequencies(self, intervals=None, axis=None):
        """ all enabled notch frequencies, optionally limited to time intervals
        and the notch filters applied to one axis """
        values = [np.array([])]
        for timestamps, frequencies, segment_axis in self.segments:
            if axis is not None and segment_axis is not None and segment_axis != axis:
                continue
            mask = np.isfinite(frequencies)
            if intervals is not None:
                mask &= _in_intervals(timestamps, intervals)
            values.append(frequencies[mask])
        return np.concatenate(values)

    def median_per_segment(self, intervals=None, axis=None):
        """ median frequency of each notch filter (ESC or FFT peak) """
        medians = []
        for timestamps, frequencies, segment_axis in self.segments:
            if axis is not None and segment_axis is not None and segment_axis != axis:
                continue
            mask = np.isfinite(frequencies)
            if intervals is not None:
                mask &= _in_intervals(timestamps, intervals)
            if np.any(mask):
                medians.append(float(np.median(frequencies[mask])))
        return medians


@dataclass
class GyroFilterConfig:
    """ notch filter tracks and static filters of the gyro filter chain """
    tracks: list
    static_notches: list # list of (name, frequency [Hz], bandwidth [Hz])
    lowpass_cutoff_hz: float
    dgyro_cutoff_hz: float
    sample_rate_hz: float # rate the filters run at, NaN if unknown
    device_id: int
    reconstructed: bool # True if derived from esc_status/sensor_gyro_fft and parameters


@dataclass
class RawGyro:
    """ gyro data before filtering: the expanded FIFO samples
    (sensor_gyro_fifo_virtual), sensor_gyro for gyros without FIFO, or the
    gyro in sensor_combined """
    topic_name: str
    instance: int
    label: str


def _get_dataset(ulog, name, instance=0):
    try:
        return ulog.get_dataset(name, instance)
    except (KeyError, IndexError, ValueError):
        return None


def _timestamps(dataset):
    if 'timestamp_sample' in dataset.data:
        return dataset.data['timestamp_sample']
    return dataset.data['timestamp']


def _sample_rate(dataset):
    """ median sample rate [Hz] of a dataset """
    t = _timestamps(dataset)
    return 1e6 / np.median(np.diff(t)) if len(t) > 1 else 0.


def _in_intervals(t, intervals):
    mask = np.zeros(len(t), dtype=bool)
    for start, end in intervals:
        mask |= (t >= start) & (t <= end)
    return mask


def _intervals_from_state(ulog, timestamps, active):
    """ (start, end) timestamps where active is set """
    intervals = []
    start = None
    for timestamp, is_active in zip(timestamps, active):
        if is_active and start is None:
            start = timestamp
        elif not is_active and start is not None:
            intervals.append((start, timestamp))
            start = None
    if start is not None:
        intervals.append((start, ulog.last_timestamp))
    return intervals if len(intervals) > 0 else None


def get_flying_intervals(ulog):
    """ :return: list of (start, end) timestamps [us] while flying (land
    detector), while armed if that is not logged, or None """
    land_detected = _get_dataset(ulog, 'vehicle_land_detected')
    if land_detected is not None:
        t = land_detected.data['timestamp']
        valid = t >= ulog.start_timestamp
        intervals = _intervals_from_state(ulog, t[valid], land_detected.data['landed'][valid] == 0)
        if intervals is not None:
            return intervals
    vehicle_status = _get_dataset(ulog, 'vehicle_status')
    if vehicle_status is None:
        return None
    return _intervals_from_state(ulog, vehicle_status.data['timestamp'],
                                 vehicle_status.data['arming_state'] == ARMING_STATE_ARMED)


def _nan_disabled(frequencies):
    frequencies = np.asarray(frequencies, dtype=np.float64).copy()
    frequencies[~(frequencies > 0)] = np.nan
    return frequencies


def _get_logged_filter_config(ulog):
    """ notch filter tracks from the gyro_filter_status topic """
    status = _get_dataset(ulog, 'gyro_filter_status')
    if status is None:
        return None
    d = status.data
    t = _timestamps(status)

    tracks = []
    num_escs = 12
    esc_bandwidth = float(np.max(d['esc_rpm_notch_bandwidth_hz']))
    for harmonic in range(int(np.max(d['esc_rpm_notch_harmonics']))):
        segments = []
        names = []
        for esc in range(num_escs):
            name = f'esc_rpm_notch_hz[{harmonic * num_escs + esc}]'
            if name in d and np.any(d[name] > 0):
                segments.append((t, _nan_disabled(d[name]), None))
                names.append(f'Motor {esc + 1}')
        if len(segments) > 0:
            tracks.append(NotchTrack(f'RPM Notch {harmonic + 1}', 'esc', harmonic, segments,
                                     esc_bandwidth, names))

    fft_bandwidth = float(np.max(d['fft_notch_bandwidth_hz']))
    for peak in range(3):
        segments = []
        for axis_index, axis in enumerate(AXES):
            frequencies = d[f'fft_notch_{axis}_hz[{peak}]']
            if np.any(frequencies > 0):
                segments.append((t, _nan_disabled(frequencies), axis_index))
        if len(segments) > 0:
            tracks.append(NotchTrack(f'FFT Notch {peak + 1}', 'fft', peak, segments,
                                     fft_bandwidth))

    static_notches = []
    for i in range(2):
        frequency = float(np.median(d[f'static_notch_hz[{i}]']))
        bandwidth = float(np.median(d[f'static_notch_bandwidth_hz[{i}]']))
        if frequency > 0:
            static_notches.append((f'Static Notch {i + 1}', frequency, bandwidth))

    return GyroFilterConfig(tracks, static_notches, float(np.median(d['lowpass_cutoff_hz'])),
                            float(ulog.initial_parameters.get('IMU_DGYRO_CUTOFF', 0.)),
                            float(np.median(d['sample_rate_hz'])), int(d['device_id'][-1]),
                            False)


def _get_reconstructed_filter_config(ulog):
    """ notch filter tracks reconstructed from esc_status, sensor_gyro_fft and
    the parameters, matching the logic in PX4 VehicleAngularVelocity """
    params = ulog.initial_parameters
    dnf_enable = int(params.get('IMU_GYRO_DNF_EN', 0))
    tracks = []

    esc_status = _get_dataset(ulog, 'esc_status')
    if esc_status is not None:
        d = esc_status.data
        t = _timestamps(esc_status)
        rpm_notch_enabled = (dnf_enable & 1) != 0
        harmonics = int(params.get('IMU_GYRO_DNF_HMC', 3)) if rpm_notch_enabled else 1
        bandwidth = float(params.get('IMU_GYRO_DNF_BW', 15.))
        freq_min = max(float(params.get('IMU_GYRO_DNF_MIN', 25.)), bandwidth)
        online_flags = d.get('esc_online_flags', np.zeros(len(t), dtype=np.uint16))

        for harmonic in range(harmonics):
            segments = []
            names = []
            for esc in range(16):
                rpm_field = f'esc[{esc}].esc_rpm'
                if rpm_field not in d:
                    break
                rpm = np.abs(d[rpm_field].astype(np.float64))
                # like PX4, an online ESC without RPM telemetry (0 rpm) keeps the
                # notch filters parked at the minimum frequency
                online = ((online_flags.astype(np.int64) >> esc) & 1).astype(bool) | (rpm > 0)
                if not np.any(online) or (not rpm_notch_enabled and not np.any(rpm > 0)):
                    continue
                motor_hz = rpm / 60.
                if rpm_notch_enabled:
                    frequencies = np.maximum(motor_hz * (harmonic + 1),
                                             freq_min + harmonic * 0.5 * bandwidth)
                else:
                    frequencies = motor_hz
                frequencies[~online] = np.nan
                segments.append((t, frequencies, None))
                names.append(f'Motor {esc + 1}')
            if len(segments) > 0:
                name = f'RPM Notch {harmonic + 1}' if rpm_notch_enabled else 'Motor RPM'
                tracks.append(NotchTrack(name, 'esc', harmonic, segments,
                                         bandwidth if rpm_notch_enabled else 0., names))

    sensor_gyro_fft = _get_dataset(ulog, 'sensor_gyro_fft')
    if sensor_gyro_fft is not None and (dnf_enable & 2) != 0:
        d = sensor_gyro_fft.data
        t = _timestamps(sensor_gyro_fft)
        bandwidth = float(np.clip(np.median(d['resolution_hz']), 8., 30.))
        for peak in range(3):
            segments = []
            for axis_index, axis in enumerate(AXES):
                frequencies = d[f'peak_frequencies_{axis}[{peak}]'].astype(np.float64)
                frequencies[~(frequencies > 10.)] = np.nan
                if np.any(np.isfinite(frequencies)):
                    segments.append((t, frequencies, axis_index))
            if len(segments) > 0:
                tracks.append(NotchTrack(f'FFT Notch {peak + 1}', 'fft', peak, segments,
                                         bandwidth))

    static_notches = []
    for i in range(2):
        frequency = float(params.get(f'IMU_GYRO_NF{i}_FRQ', 0.))
        bandwidth = float(params.get(f'IMU_GYRO_NF{i}_BW', 0.))
        if frequency > 0 and bandwidth > 0:
            static_notches.append((f'Static Notch {i + 1}', frequency, bandwidth))

    return GyroFilterConfig(tracks, static_notches, float(params.get('IMU_GYRO_CUTOFF', 0.)),
                            float(params.get('IMU_DGYRO_CUTOFF', 0.)), np.nan, 0, True)


def get_gyro_filter_config(ulog):
    """ get the notch filter tracks and static filter settings.
    Uses the logged gyro_filter_status topic if available, otherwise the
    filter state is reconstructed from esc_status, sensor_gyro_fft and the
    parameters.
    :return: GyroFilterConfig or None
    """
    try:
        config = _get_logged_filter_config(ulog)
        if config is None:
            config = _get_reconstructed_filter_config(ulog)
        return config
    except (KeyError, IndexError, ValueError) as error:
        if debug_verbose_output():
            print(type(error), "(gyro filter config):", error)
        return None


def _find_instance(ulog, topic_name, device_id):
    """ instance of topic_name with the given device_id (or the first one) """
    instances = [d for d in ulog.data_list if d.name == topic_name]
    if len(instances) == 0:
        return None
    for dataset in instances:
        if device_id != 0 and int(dataset.data['device_id'][-1]) == device_id:
            return dataset.multi_id
    return min(d.multi_id for d in instances)


def prepare_gyro_filter_analysis(ulog):
    """ get the notch filter config and find the gyro data before filtering
    of the filtered gyro (the FIFO data is added as virtual topic).
    :return: (GyroFilterConfig or None, RawGyro or None)
    """
    filter_config = get_gyro_filter_config(ulog)
    device_id = filter_config.device_id if filter_config is not None else 0

    instance = _find_instance(ulog, 'sensor_gyro_fifo', device_id)
    if instance is not None and add_virtual_fifo_topic_data(ulog, 'sensor_gyro_fifo', instance):
        return filter_config, RawGyro('sensor_gyro_fifo_virtual', instance, 'FIFO')

    # without FIFO: sensor_gyro, or the gyro in sensor_combined (not filtered either,
    # integrated at IMU_INTEG_RATE), whichever is logged at the higher rate
    candidates = []
    instance = _find_instance(ulog, 'sensor_gyro', device_id)
    if instance is not None:
        candidates.append(RawGyro('sensor_gyro', instance, 'sensor_gyro'))
    if _get_dataset(ulog, 'sensor_combined') is not None:
        candidates.append(RawGyro('sensor_combined', 0, 'sensor_combined'))
    if len(candidates) == 0:
        return filter_config, None
    return filter_config, max(candidates, key=lambda raw: _sample_rate(
        _get_dataset(ulog, raw.topic_name, raw.instance)))


def gyro_filter_raw_dataset(ulog, raw_gyro):
    """ :return: (dataset of the gyro before filtering with the fields x, y, z
    [rad/s] or None, label) """
    if raw_gyro is None:
        return None, ''
    dataset = ulog.get_dataset(raw_gyro.topic_name, raw_gyro.instance)
    if raw_gyro.topic_name == 'sensor_combined':
        data = {'timestamp': dataset.data['timestamp']}
        for i, axis in enumerate(AXES):
            data[axis] = dataset.data[f'gyro_rad[{i}]']
        dataset = SimpleNamespace(data=data)
    return dataset, raw_gyro.label


def get_gyro_filter_plots(ulog, plot_config, filter_config, raw_gyro):
    """ all gyro filter plots, in the order they are shown
    :return: list of DataPlot (finalize() may return None if data is missing)
    """
    raw_dataset, raw_label = gyro_filter_raw_dataset(ulog, raw_gyro)
    flying = get_flying_intervals(ulog)
    plots = []
    for axis_index, axis_name in enumerate(AXIS_NAMES):
        data_plot = DataPlotGyroFilterPSD(ulog.data_list, plot_config, axis_index,
                                          f'Gyro Noise {axis_name}')
        data_plot.add_graphs(raw_dataset, raw_label, filter_config, flying)
        plots.append(data_plot)

    response_plots = []
    for kind in ['magnitude', 'delay']:
        data_plot = DataPlotGyroFilterResponse(ulog.data_list, plot_config, kind)
        data_plot.add_graphs(filter_config, flying, raw_dataset)
        response_plots.append(data_plot)
    if not response_plots[0].had_error: # zoom both together
        response_plots[1].bokeh_plot.x_range = response_plots[0].bokeh_plot.x_range
    plots += response_plots

    throttle_plot = DataPlotNoiseVsThrottle(ulog, plot_config, 'vehicle_angular_velocity',
                                            'Gyro Noise vs Throttle')
    filtered = throttle_plot.dataset
    if filtered is not None:
        sources = []
        if raw_dataset is not None:
            sources.append((f'Before filtering ({raw_label})', _timestamps(raw_dataset),
                            [np.rad2deg(raw_dataset.data[axis]) for axis in AXES]))
        sources.append(('After filtering', _timestamps(filtered),
                        [np.rad2deg(filtered.data[f'xyz[{i}]']) for i in range(3)]))
        throttle_plot.add_graphs(sources, '[dB (deg/s)²/Hz]', filter_config, flying)
    plots.append(throttle_plot)

    accel_name, accel_fields = _accel_source(ulog)
    accel_plot = DataPlotNoiseVsThrottle(ulog, plot_config, accel_name,
                                         'Accelerometer Noise vs Throttle')
    if accel_plot.dataset is not None:
        accel = accel_plot.dataset
        accel_plot.add_graphs([(accel_name, _timestamps(accel),
                                [accel.data[field] for field in accel_fields])],
                              '[dB (m/s²)²/Hz]', filter_config, flying, notch_suffix=' (gyro)')
    plots.append(accel_plot)
    return plots


def _accel_source(ulog):
    """ accelerometer data with the highest rate: raw FIFO, sensor_accel or
    sensor_combined (integrated) """
    if add_virtual_fifo_topic_data(ulog, 'sensor_accel_fifo', 0):
        return 'sensor_accel_fifo_virtual', AXES
    if _get_dataset(ulog, 'sensor_accel') is not None:
        return 'sensor_accel', AXES
    return 'sensor_combined', [f'accelerometer_m_s2[{i}]' for i in range(3)]


def _downsample_segment(timestamps, frequencies, max_points):
    if len(timestamps) > max_points:
        step = int(np.ceil(len(timestamps) / max_points))
        return timestamps[::step], frequencies[::step]
    return timestamps, frequencies


def _finite_runs(timestamps, frequencies, max_points):
    """ split into parts where the notch filter is enabled, downsampled """
    finite = np.isfinite(frequencies)
    boundaries = np.flatnonzero(np.diff(finite.astype(np.int8)) != 0) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(frequencies)]))
    runs = []
    for start, end in zip(starts, ends):
        if finite[start] and end - start > 1:
            runs.append(_downsample_segment(timestamps[start:end].astype(np.float64),
                                            frequencies[start:end], max_points))
    return runs


def _track_spec_color(track):
    if track.kind == 'esc':
        return ESC_HARMONIC_SPEC_COLORS[track.index % len(ESC_HARMONIC_SPEC_COLORS)], 'solid'
    return FFT_PEAK_SPEC_COLORS[track.index % len(FFT_PEAK_SPEC_COLORS)], 'dashed'


def _track_psd_color(track):
    if track.kind == 'esc':
        return ESC_HARMONIC_PSD_COLORS[track.index % len(ESC_HARMONIC_PSD_COLORS)]
    return FFT_PEAK_PSD_COLORS[track.index % len(FFT_PEAK_PSD_COLORS)]


def _style_legend(legend, location='top_left'):
    """ :param legend: a Legend or a plot's legend """
    legend.location = location
    legend.background_fill_alpha = 0.6
    legend.label_text_font_size = '8pt'
    legend.click_policy = 'hide'
    legend.spacing = 0
    legend.padding = 4


def _track_envelope(track, num_bins):
    """ per time bin: lowest, median and highest center frequency of all notch
    filters of the track
    :return: (bin centers [us], low, median, high), NaN where all are disabled
    """
    timestamps = np.concatenate([segment[0] for segment in track.segments]).astype(np.float64)
    frequencies = np.concatenate([segment[1] for segment in track.segments])
    valid = np.isfinite(frequencies)
    timestamps, frequencies = timestamps[valid], frequencies[valid]
    if len(timestamps) == 0:
        return None
    bin_edges = np.linspace(np.min(timestamps), np.max(timestamps) + 1, num_bins + 1)
    bins = np.digitize(timestamps, bin_edges) - 1
    order = np.argsort(bins, kind='stable')
    bins, frequencies = bins[order], frequencies[order]
    low = np.full(num_bins, np.nan)
    median = np.full(num_bins, np.nan)
    high = np.full(num_bins, np.nan)
    starts = np.flatnonzero(np.diff(np.concatenate(([-1], bins))) != 0)
    for start, end in zip(starts, np.concatenate((starts[1:], [len(bins)]))):
        values = frequencies[start:end]
        low[bins[start]] = np.min(values)
        median[bins[start]] = np.median(values)
        high[bins[start]] = np.max(values)
    return (bin_edges[:-1] + bin_edges[1:]) / 2, low, median, high


def _add_legend(p, items):
    legend = Legend(items=[LegendItem(label=label, renderers=renderers)
                           for label, renderers in items.items()])
    p.add_layout(legend)
    return legend


def plot_notch_tracks(data_plot, filter_config, plot_width):
    """ draw the notch filters over a spectrogram, either per harmonic (or FFT
    peak) as the range of all notch filters widened by the notch bandwidth with
    the median center frequency, or one line per motor and harmonic
    :return: list of renderer groups (range, per motor), or None
    """
    if filter_config is None or len(filter_config.tracks) == 0 or data_plot.had_error:
        return None
    p = data_plot.bokeh_plot
    range_items = {}
    motor_items = {}
    fft_items = {}
    for track in filter_config.tracks:
        envelope = _track_envelope(track, 2 * plot_width)
        if envelope is None:
            continue
        times, low, median, high = envelope
        color, dash = _track_spec_color(track)
        renderers = []
        for run_t, run_median in _finite_runs(times, median, len(times)):
            run = (times >= run_t[0]) & (times <= run_t[-1])
            renderers.append(p.varea(x=run_t, y1=low[run] - track.bandwidth_hz / 2,
                                     y2=high[run] + track.bandwidth_hz / 2, fill_color=color,
                                     fill_alpha=0.25))
            renderers.append(p.line(run_t, run_median, line_color=color, line_width=1.5,
                                    line_alpha=0.9, line_dash=dash))
        (fft_items if track.kind == 'fft' else range_items)[track.name] = renderers

        if track.kind != 'esc':
            continue
        for i, (timestamps, frequencies, _) in enumerate(track.segments):
            name = track.segment_names[i] if i < len(track.segment_names) else f'Motor {i + 1}'
            color = MOTOR_SPEC_COLORS[i % len(MOTOR_SPEC_COLORS)]
            for run_t, run_f in _finite_runs(timestamps, frequencies, 2 * plot_width):
                motor_items.setdefault(name, []).append(p.line(
                    run_t, run_f, line_color=color, line_width=1, line_alpha=0.8))

    groups = []
    for items in [range_items, motor_items]:
        if len(items) == 0:
            continue
        items = {**items, **fft_items}
        legend = _add_legend(p, items)
        _style_legend(legend)
        # the legend last: it draws its items faded if they are hidden when it is shown
        groups.append([r for renderers in items.values() for r in renderers] + [legend])
    if len(groups) == 0 and len(fft_items) > 0:
        legend = _add_legend(p, fft_items)
        _style_legend(legend)
        groups.append([r for renderers in fft_items.values() for r in renderers] + [legend])
    for group in groups[1:]:
        for renderer in group:
            renderer.visible = False
    return groups


def _runs(t, mask, max_gap_us):
    """ :return: list of (start, end) index ranges where mask is set and there
    are no time gaps above max_gap_us """
    boundaries = np.flatnonzero((np.diff(mask.astype(np.int8)) != 0)
                                | (np.diff(t) > max_gap_us)) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(t)]))
    return [(start, end) for start, end in zip(starts, ends) if mask[start]]


def welch_psd(t, values, intervals=None, resolution_hz=2.):
    """ Welch power spectral density, averaged over all contiguous parts of the
    data (logging dropouts and parts outside of intervals are excluded).
    :param t: timestamps [us]
    :return: (frequencies, psd, sampling frequency) or None
    """
    if len(t) < 2:
        return None
    dt_us = np.median(np.diff(t))
    if dt_us <= 0:
        return None
    sample_rate = 1e6 / dt_us
    nperseg = int(2 ** np.round(np.log2(sample_rate / resolution_hz)))
    nperseg = int(np.clip(nperseg, 256, 8192))

    mask = np.ones(len(t), dtype=bool) if intervals is None else _in_intervals(t, intervals)
    psd_sum = None
    num_used = 0
    frequencies = None
    for start, end in _runs(t, mask, 3 * dt_us):
        if end - start < nperseg:
            continue
        x = values[start:end]
        frequencies, psd = scipy.signal.welch(x - np.mean(x), fs=sample_rate, window='hann',
                                              nperseg=nperseg, noverlap=nperseg // 2,
                                              scaling='density')
        psd_sum = psd * (end - start) if psd_sum is None else psd_sum + psd * (end - start)
        num_used += end - start
    if psd_sum is None:
        return None
    return frequencies, psd_sum / num_used, sample_rate


def initial_view_max_hz(filter_config, min_view_hz=1000.):
    """ upper frequency of the initial view: the motor noise, notch filters
    and controller bandwidth are typically all below 1 kHz, while the raw
    gyro can go up to several kHz """
    view_max = min_view_hz
    if filter_config is not None:
        for track in filter_config.tracks:
            frequencies = track.valid_frequencies()
            if len(frequencies) > 0:
                view_max = max(view_max, 1.2 * np.max(frequencies))
    return view_max


def _mark_frequency(p, frequency, label, dash, y_screen_offset):
    p.add_layout(Span(location=frequency, dimension='height', line_color='black',
                      line_dash=dash, line_width=1))
    p.add_layout(Label(x=frequency, y=10 + y_screen_offset, text=' ' + label,
                       y_units='screen', level='glyph', text_font_size='8pt',
                       text_color='black'))


def _mark_filter_cutoffs(p, filter_config, nyquist_hz):
    """ vertical lines for the low-pass filters and the controller Nyquist frequency """
    if nyquist_hz is not None:
        _mark_frequency(p, nyquist_hz, 'Nyquist', 'dotted', 0)
    if filter_config is None:
        return
    if filter_config.lowpass_cutoff_hz > 0:
        _mark_frequency(p, filter_config.lowpass_cutoff_hz, 'Gyro LPF', 'dashed', 15)
    if filter_config.dgyro_cutoff_hz > 0:
        _mark_frequency(p, filter_config.dgyro_cutoff_hz, 'D-term LPF', 'dashdot', 30)


class DataPlotGyroFilterPSD(DataPlot):
    """
    Power spectral density of one gyro axis while flying, before and after
    filtering, with the frequency range of each notch filter
    group and the low-pass filters.
    """

    def __init__(self, data, config, axis_index, title, plot_height='small'):
        super().__init__(data, config, 'vehicle_angular_velocity', x_axis_label='[Hz]',
                         y_axis_label='[dB (deg/s)²/Hz]', title=title,
                         plot_height=plot_height)
        self._use_time_formatter = False
        self._axis_index = axis_index

    def add_graphs(self, raw_dataset, raw_label, filter_config, intervals):
        """ plot the spectra, notch filter ranges and filter frequencies """
        if self._had_error: return
        try:
            p = self._p
            filtered = welch_psd(_timestamps(self._cur_dataset),
                                 np.rad2deg(self._cur_dataset.data[f'xyz[{self._axis_index}]']),
                                 intervals)
            raw = None
            if raw_dataset is not None:
                raw = welch_psd(_timestamps(raw_dataset),
                                np.rad2deg(raw_dataset.data[AXES[self._axis_index]]), intervals)
            if filtered is None or filtered[2] < 100: # default logging rate is too low
                self._had_error = True
                return

            f_post, psd_post, fs_post = filtered
            spectra = []
            x_max = fs_post / 2
            if raw is not None:
                f_raw, psd_raw, fs_raw = raw
                spectra.append((f_raw, psd_raw, '#999999', 'Before filtering'))
                x_max = fs_raw / 2
            spectra.append((f_post, psd_post, '#0072b2', 'After filtering'))

            y_min = np.inf
            y_max = -np.inf
            for frequencies, psd, color, label in spectra:
                psd_db = 10 * np.log10(np.maximum(psd, 1e-12))
                valid = frequencies > 1.
                y_min = min(y_min, np.percentile(psd_db[valid], 1))
                y_max = max(y_max, np.max(psd_db[valid]))
                p.line(frequencies, psd_db, line_color=color, line_width=1.5, alpha=0.9,
                       legend_label=label)
            y_min -= 5
            y_max += 5
            p.y_range = Range1d(y_min, y_max)
            p.x_range = Range1d(0, min(x_max, initial_view_max_hz(filter_config)),
                                bounds=(0, x_max))

            if filter_config is not None:
                self._add_notch_ranges(filter_config, intervals, y_min, y_max)
            _mark_filter_cutoffs(p, filter_config, fs_post / 2)
            _style_legend(p.legend, 'top_right')

        except (KeyError, IndexError, ValueError, ZeroDivisionError) as error:
            if debug_verbose_output():
                print(type(error), "(gyro filter PSD):", error)
            self._had_error = True

    def _add_notch_ranges(self, filter_config, intervals, y_min, y_max):
        """ each notch filter group as a region from the 10th to the 90th
        percentile of its frequency while flying, widened by the notch
        bandwidth, and a line at the median """
        p = self._p
        for track in filter_config.tracks:
            frequencies = track.valid_frequencies(intervals, self._axis_index)
            if len(frequencies) == 0:
                continue
            low, median, high = np.percentile(frequencies, [10, 50, 90])
            color = _track_psd_color(track)
            p.quad(left=[low - track.bandwidth_hz / 2], right=[high + track.bandwidth_hz / 2],
                   bottom=[y_min], top=[y_max], fill_color=color, fill_alpha=0.15,
                   line_alpha=0, legend_label=track.name)
            p.add_layout(Span(location=median, dimension='height', line_color=color,
                              line_alpha=0.9, line_width=2))

        for name, frequency, bandwidth in filter_config.static_notches:
            p.quad(left=[frequency - bandwidth / 2], right=[frequency + bandwidth / 2],
                   bottom=[y_min], top=[y_max], fill_color='black', fill_alpha=0.1,
                   line_alpha=0, hatch_pattern='/', hatch_alpha=0.3, legend_label=name)


def _lowpass2p(sample_rate, cutoff):
    """ PX4 LowPassFilter2p (2nd order Butterworth) coefficients """
    if cutoff <= 0 or cutoff >= sample_rate / 2:
        return [1.], [1.]
    ohm = np.tan(np.pi * cutoff / sample_rate)
    norm = 1. + 2. * np.cos(np.pi / 4.) * ohm + ohm * ohm
    gain = ohm * ohm / norm
    return ([gain, 2. * gain, gain],
            [1., 2. * (ohm * ohm - 1.) / norm,
             (1. - 2. * np.cos(np.pi / 4.) * ohm + ohm * ohm) / norm])


def _notch(sample_rate, frequency, bandwidth):
    """ PX4 NotchFilter coefficients """
    if frequency <= 0 or bandwidth <= 0 or frequency >= sample_rate / 2:
        return [1.], [1.]
    alpha = np.tan(np.pi * bandwidth / sample_rate)
    beta = -np.cos(2. * np.pi * frequency / sample_rate)
    a0_inv = 1. / (alpha + 1.)
    return ([a0_inv, 2. * beta * a0_inv, a0_inv],
            [1., 2. * beta * a0_inv, (1. - alpha) * a0_inv])


def _first_order(sample_rate, cutoff):
    """ PX4 AlphaFilter (first order low-pass) coefficients """
    if cutoff <= 0:
        return [1.], [1.]
    dt = 1. / sample_rate
    alpha = dt / (dt + 1. / (2. * np.pi * cutoff))
    return [alpha], [1., alpha - 1.]


def gyro_filter_response(filter_config, sample_rate, frequencies, intervals, axis):
    """ frequency response of the gyro filters and of the D-term filters
    (gyro filters, backward difference and IMU_DGYRO_CUTOFF), with the
    dynamic notch filters at their median frequency while flying.
    :return: (gyro response, D-term response without the differentiation)
    """
    filters = [_lowpass2p(sample_rate, filter_config.lowpass_cutoff_hz)]
    for _, frequency, bandwidth in filter_config.static_notches:
        filters.append(_notch(sample_rate, frequency, bandwidth))
    for track in filter_config.tracks:
        if track.bandwidth_hz <= 0:
            continue
        for frequency in track.median_per_segment(intervals, axis):
            filters.append(_notch(sample_rate, frequency, track.bandwidth_hz))

    gyro = np.ones(len(frequencies), dtype=complex)
    for numerator, denominator in filters:
        gyro *= scipy.signal.freqz(numerator, denominator, worN=frequencies, fs=sample_rate)[1]

    # backward difference: delay of half a sample compared to a true derivative
    half_sample = np.exp(-1j * np.pi * frequencies / sample_rate)
    numerator, denominator = _first_order(sample_rate, filter_config.dgyro_cutoff_hz)
    d_term = gyro * half_sample * scipy.signal.freqz(numerator, denominator, worN=frequencies,
                                                     fs=sample_rate)[1]
    return gyro, d_term


def phase_delay_ms(response, frequencies, frequency):
    """ phase delay [ms] of a frequency response at the given frequency """
    phase = np.unwrap(np.angle(response))
    return float(-np.interp(frequency, frequencies, phase) / (2 * np.pi * frequency) * 1e3)


class DataPlotGyroFilterResponse(DataPlot):
    """
    Magnitude (kind 'magnitude') or delay (kind 'delay') of the gyro and
    D-term filters (roll axis), with the dynamic notch filters at their median
    frequency while flying.
    """

    def __init__(self, data, config, kind):
        title = 'Gyro Filter Response' if kind == 'magnitude' else 'Gyro Filter Delay'
        y_label = 'Magnitude [dB]' if kind == 'magnitude' else 'Delay [ms]'
        super().__init__(data, config, 'vehicle_angular_velocity', x_axis_label='[Hz]',
                         y_axis_label=y_label, title=title, plot_height='small')
        self._use_time_formatter = False
        self._kind = kind

    def add_graphs(self, filter_config, intervals, raw_dataset):
        """ plot the filter magnitude or delay """
        if self._had_error: return
        if filter_config is None:
            self._had_error = True
            return
        try:
            p = self._p
            sample_rate = filter_config.sample_rate_hz
            if not np.isfinite(sample_rate) and raw_dataset is not None:
                sample_rate = 1e6 / np.median(np.diff(_timestamps(raw_dataset)))
            if not np.isfinite(sample_rate) or sample_rate < 100:
                self._had_error = True
                return
            frequencies = np.linspace(0.5, min(sample_rate / 2, 1000.) * 0.999, 2000)
            responses = gyro_filter_response(filter_config, sample_rate, frequencies,
                                             intervals, 0)
            p.x_range = Range1d(0, frequencies[-1], bounds=(0, frequencies[-1]))
            colors = ['#0072b2', '#d55e00']
            labels = ['Gyro', 'D-term']

            if self._kind == 'magnitude':
                magnitudes = [20 * np.log10(np.maximum(np.abs(response), 1e-6))
                              for response in responses]
                # fit the smooth part of the curves, the notches go down to -inf
                y_min = min(np.percentile(magnitude, 25) for magnitude in magnitudes)
                p.y_range = Range1d(max(10 * np.floor(y_min / 10) - 10, -100), 5)
                for magnitude, color, label in zip(magnitudes, colors, labels):
                    p.line(frequencies, magnitude, line_color=color, line_width=2,
                           legend_label=label)
            else:
                delays = []
                for response, color, label in zip(responses, colors, labels):
                    delay = -np.unwrap(np.angle(response)) / (2 * np.pi * frequencies) * 1e3
                    delay_at = phase_delay_ms(response, frequencies, DELAY_FREQUENCY_HZ)
                    p.line(frequencies, delay, line_color=color, line_width=2,
                           legend_label=f'{label}: {delay_at:.1f} ms at '
                           f'{DELAY_FREQUENCY_HZ:.0f} Hz')
                    delays.append(delay)
                # the delay jumps around the notch filters, fit the rest
                y_max = max(np.percentile(delay, 95) for delay in delays)
                p.y_range = Range1d(0, max(1.2 * y_max, 1.))
                p.add_layout(Span(location=DELAY_FREQUENCY_HZ, dimension='height',
                                  line_color='gray', line_dash='dotted', line_width=1))
            _mark_filter_cutoffs(p, filter_config, None)
            _style_legend(p.legend, 'top_right' if self._kind == 'magnitude' else 'bottom_right')

        except (KeyError, IndexError, ValueError, ZeroDivisionError) as error:
            if debug_verbose_output():
                print(type(error), "(gyro filter response):", error)
            self._had_error = True


def _stft(timestamps, values_list, resolution_hz, overlap=0.5):
    """ short time PSD of the sum of the given signals
    :param overlap: overlap of neighboring windows (0.5 = half a window)
    :return: (time [us], frequencies, psd) or None
    """
    dt_diff = np.diff(timestamps)
    delta_t = np.median(dt_diff) * 1e-6
    if len(timestamps) < 2 or delta_t <= 0:
        return None
    sample_rate = 1. / delta_t
    if sample_rate < 100: # default logging rate is too low
        return None
    window_length = int(np.clip(2 ** np.round(np.log2(sample_rate / resolution_hz)), 256, 2048))
    psd_sum = None
    for values in values_list:
        frequencies, time, psd = scipy.signal.spectrogram(
            values, fs=sample_rate, window='hann', nperseg=window_length,
            noverlap=int(window_length * overlap), scaling='density')
        psd_sum = psd if psd_sum is None else psd_sum + psd
    # stretch by mean/median to realign with the elapsed time after logging dropouts
    time = time * (np.mean(dt_diff) * 1e-6 / delta_t) * 1e6 + timestamps[0]
    return time, frequencies, psd_sum


def gyro_spectrogram(timestamps, xyz, resolution_hz, max_columns):
    """ spectrogram of the sum of the 3 axes in dB
    :return: (time [us], frequencies, image [dB]) or None
    """
    stft = _stft(timestamps, xyz, resolution_hz)
    if stft is None:
        return None
    time, frequencies, psd_sum = stft
    if len(time) > max_columns: # average neighboring columns
        step = int(np.ceil(len(time) / max_columns))
        num = len(time) // step
        time = time[:num * step:step]
        psd_sum = psd_sum[:, :num * step].reshape(len(frequencies), num, step).mean(axis=2)
    image = 10 * np.log10(np.maximum(psd_sum, 1e-20))
    return time, frequencies, image.astype(np.float32)


def toggle_renderers(labels, groups):
    """ buttons to show one of the groups of renderers (or legends); the
    renderers of all other groups are hidden. A group's legend goes last. """
    toggle = RadioButtonGroup(labels=labels, active=0)
    toggle.js_on_event('button_click', CustomJS(
        args={'groups': groups, 'toggle': toggle}, code="""
        for (let i = 0; i < groups.length; i++) {
            if (i != toggle.active) {
                for (const model of groups[i]) { model.visible = false; }
            }
        }
        for (const model of groups[toggle.active]) { model.visible = true; }"""))
    return toggle


def _add_color_bar(p, color_mapper, title='[dB]'):
    p.add_layout(ColorBar(color_mapper=color_mapper, major_label_text_font_size='5pt',
                          ticker=BasicTicker(desired_num_ticks=5),
                          formatter=PrintfTickFormatter(format='%.0f'), title=title,
                          label_standoff=6, border_line_color=None, location=(0, 0)),
                 'right')


def _set_zoom_tools(p):
    wheel_zoom = WheelZoomTool()
    p.toolbar.tools = [PanTool(), wheel_zoom, BoxZoomTool(), ResetTool(), SaveTool()]
    p.toolbar.active_scroll = wheel_zoom
    p.toolbar_location = 'above'


class DataPlotWithToggle(DataPlot):
    """ a DataPlot with buttons above it """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._toggles = []

    @property
    def layout(self):
        """ the plot with the buttons above it """
        if len(self._toggles) == 0:
            return self._p
        return column(row(*self._toggles), self._p)


class DataPlotGyroSpectrogram(DataPlotWithToggle):
    """
    Gyro spectrogram (sum of all axes) before and after filtering, with a
    button to switch between them. Both use the same color scale, so the
    noise reduction is visible as a change in color.
    """

    def __init__(self, data, config, x_range, title):
        super().__init__(data, config, 'vehicle_angular_velocity', y_axis_label='[Hz]',
                         title=title, plot_height='normal', x_range=x_range)

    def add_graphs(self, raw_dataset, raw_label, filter_config):
        """ plot the spectrograms and the notch filters """
        if self._had_error: return
        try:
            p = self._p
            max_columns = 2 * self._config['plot_width']
            spectrograms = []
            if raw_dataset is not None:
                spectrograms.append((f'Before filtering ({raw_label})', gyro_spectrogram(
                    _timestamps(raw_dataset), [raw_dataset.data[axis] for axis in AXES],
                    4., max_columns)))
            spectrograms.append(('After filtering', gyro_spectrogram(
                _timestamps(self._cur_dataset),
                [self._cur_dataset.data[f'xyz[{i}]'] for i in range(3)], 4., max_columns)))
            spectrograms = [(label, spec) for label, spec in spectrograms if spec is not None]
            if len(spectrograms) == 0:
                self._had_error = True
                return

            # same color scale for both, so the noise reduction is visible
            all_values = np.concatenate([spec[2].ravel() for _, spec in spectrograms])
            color_mapper = LinearColorMapper(palette='Viridis256',
                                             low=float(np.percentile(all_values, 1)),
                                             high=float(np.max(all_values)))
            renderers = []
            max_frequency = 0
            for i, (label, (time, frequencies, image)) in enumerate(spectrograms):
                renderer = p.image(image=[image], x=time[0], y=frequencies[0],
                                   dw=time[-1] - time[0], dh=frequencies[-1] - frequencies[0],
                                   color_mapper=color_mapper)
                renderer.visible = i == 0
                renderers.append(renderer)
                max_frequency = max(max_frequency, frequencies[-1])

            p.y_range = Range1d(0, min(max_frequency, initial_view_max_hz(filter_config)),
                                bounds=(0, max_frequency))
            _add_color_bar(p, color_mapper)
            if len(renderers) > 1:
                self._toggles.append(toggle_renderers(
                    [label for label, _ in spectrograms], [[r] for r in renderers]))
            _set_zoom_tools(p)
            notch_groups = plot_notch_tracks(self, filter_config, self._config['plot_width'])
            if notch_groups is not None:
                labels = ['Notch range', 'Per motor'][:len(notch_groups)] + ['Hide notches']
                self._toggles.append(toggle_renderers(labels, notch_groups + [[]]))

        except (KeyError, IndexError, ValueError, ZeroDivisionError) as error:
            if debug_verbose_output():
                print(type(error), "(gyro spectrogram):", error)
            self._had_error = True


def get_throttle(ulog):
    """ collective throttle [0, 100] over time: mean of the motor outputs, or
    the thrust setpoint
    :return: (timestamps, throttle) or None
    """
    motors = _get_dataset(ulog, 'actuator_motors')
    if motors is not None:
        controls = [motors.data[f'control[{i}]'] for i in range(12)
                    if f'control[{i}]' in motors.data
                    and np.any(np.isfinite(motors.data[f'control[{i}]']))
                    and np.any(motors.data[f'control[{i}]'] != 0)]
        if len(controls) > 0:
            return motors.data['timestamp'], np.clip(np.nanmean(controls, axis=0), 0, 1) * 100
    thrust = _get_dataset(ulog, 'vehicle_thrust_setpoint')
    if thrust is not None:
        return thrust.data['timestamp'], np.clip(-thrust.data['xyz[2]'], 0, 1) * 100
    return None


def _fill_small_gaps(image, max_gap=MAX_THROTTLE_GAP_BINS):
    """ interpolate missing throttle bins (columns) between flown throttles,
    if at most max_gap bins are missing """
    filled = np.flatnonzero(np.all(np.isfinite(image), axis=0))
    for left, right in zip(filled[:-1], filled[1:]):
        if 1 < right - left <= max_gap + 1:
            weights = (np.arange(left + 1, right) - left) / (right - left)
            image[:, left + 1:right] = (image[:, [left]] * (1 - weights)
                                        + image[:, [right]] * weights)
    return image


class DataPlotNoiseVsThrottle(DataPlotWithToggle):
    """
    Noise spectrum over throttle while flying: motor noise moves up in
    frequency with throttle, a frame resonance stays at the same frequency.
    The notch filter frequencies are drawn as lines.
    """

    THROTTLE_BIN_PERCENT = 2.

    def __init__(self, ulog, config, data_name, title):
        super().__init__(ulog.data_list, config, data_name, x_axis_label='Throttle [%]',
                         y_axis_label='Frequency [Hz]', title=title, plot_height='normal')
        self._use_time_formatter = False
        self._throttle = get_throttle(ulog)

    def add_graphs(self, sources, unit_label, filter_config, intervals, notch_suffix=''):
        """ :param sources: list of (label, timestamps, list of signals), the
        spectra of the signals are summed """
        if self._had_error: return
        if self._throttle is None:
            self._had_error = True
            return
        try:
            p = self._p
            bin_edges = np.arange(0, 100 + self.THROTTLE_BIN_PERCENT, self.THROTTLE_BIN_PERCENT)
            images = []
            for label, timestamps, signals in sources:
                # short, strongly overlapping windows: throttle changes quickly
                # (e.g. while taking off), each throttle should get some windows
                stft = _stft(timestamps, signals, 8., overlap=7 / 8)
                if stft is None:
                    continue
                time, frequencies, psd = stft
                throttle = np.interp(time, self._throttle[0], self._throttle[1])
                valid = np.ones(len(time), dtype=bool) if intervals is None \
                    else _in_intervals(time, intervals)
                image = np.full((len(frequencies), len(bin_edges) - 1), np.nan)
                bins = np.digitize(throttle, bin_edges) - 1
                for i in range(len(bin_edges) - 1):
                    columns = valid & (bins == i)
                    if np.any(columns):
                        image[:, i] = 10 * np.log10(np.maximum(
                            psd[:, columns].mean(axis=1), 1e-20))
                images.append((label, frequencies, _fill_small_gaps(image).astype(np.float32)))
            if len(images) == 0 or all(np.all(np.isnan(image)) for _, _, image in images):
                self._had_error = True
                return

            all_values = np.concatenate([image[np.isfinite(image)] for _, _, image in images])
            color_mapper = LinearColorMapper(palette='Viridis256',
                                             low=float(np.percentile(all_values, 1)),
                                             high=float(np.max(all_values)),
                                             nan_color='rgba(0, 0, 0, 0)')
            renderers = []
            max_frequency = 0
            for i, (label, frequencies, image) in enumerate(images):
                renderer = p.image(image=[image], x=0, y=frequencies[0], dw=100,
                                   dh=frequencies[-1] - frequencies[0],
                                   color_mapper=color_mapper)
                renderer.visible = i == 0
                renderers.append(renderer)
                max_frequency = max(max_frequency, frequencies[-1])
            p.x_range = Range1d(0, 100)
            p.y_range = Range1d(0, min(max_frequency, initial_view_max_hz(filter_config)),
                                bounds=(0, max_frequency))
            _add_color_bar(p, color_mapper, unit_label)
            if len(renderers) > 1:
                self._toggles.append(toggle_renderers([label for label, _, _ in images],
                                                       [[r] for r in renderers]))
            _set_zoom_tools(p)
            self._plot_notches_over_throttle(filter_config, intervals, bin_edges, notch_suffix)

        except (KeyError, IndexError, ValueError, ZeroDivisionError) as error:
            if debug_verbose_output():
                print(type(error), "(noise vs throttle):", error)
            self._had_error = True

    def _plot_notches_over_throttle(self, filter_config, intervals, bin_edges, suffix):
        """ median notch filter frequency per throttle bin """
        if filter_config is None:
            return
        p = self._p
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        for track in filter_config.tracks:
            frequencies = []
            throttles = []
            for timestamps, track_frequencies, _ in track.segments:
                mask = np.isfinite(track_frequencies)
                if intervals is not None:
                    mask &= _in_intervals(timestamps, intervals)
                frequencies.append(track_frequencies[mask])
                throttles.append(np.interp(timestamps[mask], self._throttle[0],
                                           self._throttle[1]))
            frequencies = np.concatenate(frequencies)
            throttles = np.concatenate(throttles)
            if len(frequencies) == 0:
                continue
            bins = np.digitize(throttles, bin_edges) - 1
            medians = np.array([np.median(frequencies[bins == i]) if np.any(bins == i)
                                else np.nan for i in range(len(bin_centers))])
            color, dash = _track_spec_color(track)
            p.line(bin_centers, medians, line_color=color, line_width=1.5, line_alpha=0.8,
                   line_dash=dash, legend_label=track.name + suffix)
        if len(p.legend) > 0:
            _style_legend(p.legend)
