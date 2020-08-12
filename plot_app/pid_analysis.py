""" PID response analysis """

import colorsys

import numpy as np

from bokeh.models import Range1d, Span, LinearColorMapper, ColumnDataSource, LabelSet
from scipy.interpolate import interp1d
from scipy.ndimage.filters import gaussian_filter1d

from config import colors3
from plotting import DataPlot

# keep the same formatting as the original code
# pylint: skip-file

# Source: https://github.com/Plasmatree/PID-Analyzer
# "THE BEER-WARE LICENSE" (Revision 42):
# <florian.melsheimer@gmx.de> wrote this file. As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return. Florian Melsheimer

class Trace:
    """ PID response analysis based on a deconvolution using a
    setpoint and the measured process variable as inputs.
    It computes an average, stdev and a 2D histogram.
    """
    framelen = 1.           # length of each single frame over which to compute response
    resplen = 0.5           # length of respose window
    cutfreq = 25.           # cutfreqency of what is considered as input
    tuk_alpha = 1.0         # alpha of tukey window, if used
    superpos = 16           # sub windowing (superpos windows in framelen)
    threshold = 500.        # threshold for 'high input rate'
    noise_framelen = 0.3    # window width for noise analysis
    noise_superpos = 16     # subsampling for noise analysis windows

    def __init__(self, name, time, gyro_rate, gyro_setpoint, throttle,
                 d_err=None, debug=None):
        """Initialize a Trace object, that does the analysis for a single axis.

        Note: all data arrays must have the same length as time

        :param name: axis name (e.g. roll)
        :param time: np array with sampling times [s]
        :param gyro_rate: np array with the gyro rates [deg/s]
        :param throttle: np array with the throttle input [0, 100]

        :param d_err: np array with D term error (optional)
        :param debug: TODO
        """

        # equally space samples in time
        data = {
            'gyro': gyro_rate,
            'input': gyro_setpoint,
            'throttle': throttle
            }
        if d_err is not None: data['d_err'] = d_err
        if debug is not None: data['debug'] = debug
        self.time, self.data = self.equalize_data(time, data)
        self.gyro = self.data['gyro']
        self.input = self.data['input']
        self.throttle = self.data['throttle']
        self.dt = self.time[0]-self.time[1]

        self.data['time'] = self.time

        self.name = name

        #enable this to generate artifical gyro trace with known system response
        #self.gyro=self.toy_out(self.input, delay=0.01, mode='normal')####

        self.flen = self.stepcalc(self.time, Trace.framelen)        # array len corresponding to framelen in s
        self.rlen = self.stepcalc(self.time, Trace.resplen)         # array len corresponding to resplen in s
        self.time_resp = self.time[0:self.rlen]-self.time[0]

        self.stacks = self.winstacker({'time':[],'input':[],'gyro':[], 'throttle':[]}, self.flen, Trace.superpos)                                  # [[time, input, output],]
        self.window = np.hanning(self.flen)                                     #self.tukeywin(self.flen, self.tuk_alpha)
        self.spec_sm, self.avr_t, self.avr_in, self.max_in, self.max_thr = self.stack_response(self.stacks, self.window)
        self.low_mask, self.high_mask = self.low_high_mask(self.max_in, self.threshold)       #calcs masks for high and low inputs according to threshold
        self.toolow_mask = self.low_high_mask(self.max_in, 20)[1]          #mask for ignoring noisy low input

# commented, because it's unused
#        self.resp_sm = self.weighted_mode_avr(self.spec_sm, self.toolow_mask, [-1.5,3.5], 1000)
#        self.resp_quality = -self.to_mask((np.abs(self.spec_sm -self.resp_sm[0]).mean(axis=1)).clip(0.5-1e-9,0.5))+1.
#        # masking by setting trottle of unwanted traces to neg
#        self.thr_response = self.hist2d(self.max_thr * (2. * (self.toolow_mask*self.resp_quality) - 1.), self.time_resp,
#                                        (self.spec_sm.transpose() * self.toolow_mask).transpose(), [101, self.rlen])

        self.resp_low = self.weighted_mode_avr(self.spec_sm, self.low_mask*self.toolow_mask, [-1.5,3.5], 1000)
        if self.high_mask.sum()>0:
            self.resp_high = self.weighted_mode_avr(self.spec_sm, self.high_mask*self.toolow_mask, [-1.5,3.5], 1000)

        if 'd_err' in self.data:
            self.noise_winlen = self.stepcalc(self.time, Trace.noise_framelen)
            self.noise_stack = self.winstacker({'time':[], 'gyro':[], 'throttle':[], 'd_err':[], 'debug':[]},
                                               self.noise_winlen, Trace.noise_superpos)
            self.noise_win = np.hanning(self.noise_winlen)

            self.noise_gyro = self.stackspectrum(self.noise_stack['time'],self.noise_stack['throttle'],self.noise_stack['gyro'], self.noise_win)
            self.noise_d = self.stackspectrum(self.noise_stack['time'], self.noise_stack['throttle'], self.noise_stack['d_err'], self.noise_win)
            self.noise_debug = self.stackspectrum(self.noise_stack['time'], self.noise_stack['throttle'], self.noise_stack['debug'], self.noise_win)
            if self.noise_debug['hist2d'].sum()>0:
                ## mask 0 entries
                thr_mask = self.noise_gyro['throt_hist_avr'].clip(0,1)
                self.filter_trans = np.average(self.noise_gyro['hist2d'], axis=1, weights=thr_mask)/\
                                    np.average(self.noise_debug['hist2d'], axis=1, weights=thr_mask)
            else:
                self.filter_trans = self.noise_gyro['hist2d'].mean(axis=1)*0.

    @staticmethod
    def low_high_mask(signal, threshold):
        low = np.copy(signal)

        low[low <=threshold] = 1.
        low[low > threshold] = 0.
        high = -low+1.

        if high.sum() < 10:     # ignore high pinput that is too short
            high *= 0.

        return low, high

    def to_mask(self, clipped):
        clipped-=clipped.min()
        clipped_max = clipped.max()
        if clipped_max > 1e-10: # avoid division by zero
            clipped/=clipped_max
        return clipped


    def rate_curve(self, rcin, inmax=500., outmax=800., rate=160.):
        ### an estimated rate curve. not used.
        expoin = (np.exp((rcin - inmax) / rate) - np.exp((-rcin - inmax) / rate)) * outmax
        return expoin


    def tukeywin(self, len, alpha=0.5):
        ### makes tukey widow for envelopig
        M = len
        n = np.arange(M - 1.)  #
        if alpha <= 0:
            return np.ones(M)  # rectangular window
        elif alpha >= 1:
            return np.hanning(M)

        # Normal case
        x = np.linspace(0, 1, M, dtype=np.float64)
        w = np.ones(x.shape)

        # first condition 0 <= x < alpha/2
        first_condition = x < alpha / 2
        w[first_condition] = 0.5 * (1 + np.cos(2 * np.pi / alpha * (x[first_condition] - alpha / 2)))

        # second condition already taken care of

        # third condition 1 - alpha / 2 <= x <= 1
        third_condition = x >= (1 - alpha / 2)
        w[third_condition] = 0.5 * (1 + np.cos(2 * np.pi / alpha * (x[third_condition] - 1 + alpha / 2)))

        return w

    def toy_out(self, inp, delay=0.01, length=0.01, noise=5., mode='normal', sinfreq=100.):
        # generates artificial output for benchmarking
        freq= 1./(self.time[1]-self.time[0])
        toyresp = np.zeros(int((delay+length)*freq))
        toyresp[int((delay)*freq):]=1.
        toyresp/=toyresp.sum()
        toyout = np.convolve(inp, toyresp, mode='full')[:len(inp)]#*0.9
        if mode=='normal':
            noise_sig = (np.random.random_sample(len(toyout))-0.5)*noise
        elif mode=='sin':
            noise_sig = (np.sin(2.*np.pi*self.time*sinfreq)) * noise
        else:
            noise_sig=0.
        return toyout+noise_sig


    @staticmethod
    def equalize_data(time, data):
        """Resample & interpolate all dict elements in data for equal sampling in time

        :return: tuple of (time, data)
        """
        newtime = np.linspace(time[0], time[-1], len(time), dtype=np.float64)
        output = {}
        for key in data:
            output[key] = interp1d(time, data[key])(newtime)
        return (newtime, output)


    def stepcalc(self, time, duration):
        ### calculates frequency and resulting windowlength
        tstep = (time[-1]-time[0])/len(time)
        freq = 1./tstep
        arr_len = duration * freq
        return int(arr_len)

    def winstacker(self, stackdict, flen, superpos):
        ### makes stack of windows for deconvolution
        tlen = len(self.time)
        shift = int(flen/superpos)
        wins = int((tlen-flen)/shift)
        for i in np.arange(wins):
            for key in stackdict.keys():
                stackdict[key].append(self.data[key][i * shift:i * shift + flen])
        for k in stackdict.keys():
            #print('key',k)
            #print(len(stackdict[k]))
            stackdict[k]=np.array(stackdict[k], dtype=np.float64)
        return stackdict

    def wiener_deconvolution(self, input, output, cutfreq):      # input/output are two-dimensional
        pad = 1024 - (len(input[0]) % 1024)                     # padding to power of 2, increases transform speed
        input = np.pad(input, [[0,0],[0,pad]], mode='constant')
        output = np.pad(output, [[0, 0], [0, pad]], mode='constant')
        H = np.fft.fft(input, axis=-1)
        G = np.fft.fft(output,axis=-1)
        freq = np.abs(np.fft.fftfreq(len(input[0]), self.dt))
        sn = self.to_mask(np.clip(np.abs(freq), cutfreq-1e-9, cutfreq))
        len_lpf=np.sum(np.ones_like(sn)-sn)
        sn=self.to_mask(gaussian_filter1d(sn,len_lpf/6.))
        sn= 10.*(-sn+1.+1e-9)       # +1e-9 to prohibit 0/0 situations
        Hcon = np.conj(H)
        deconvolved_sm = np.real(np.fft.ifft(G * Hcon / (H * Hcon + 1./sn),axis=-1))
        return deconvolved_sm

    def stack_response(self, stacks, window):
        inp = stacks['input'] * window
        outp = stacks['gyro'] * window
        thr = stacks['throttle'] * window

        deconvolved_sm = self.wiener_deconvolution(inp, outp, self.cutfreq)[:, :self.rlen]
        delta_resp = deconvolved_sm.cumsum(axis=1)

        max_thr = np.abs(np.abs(thr)).max(axis=1)
        avr_in = np.abs(np.abs(inp)).mean(axis=1)
        max_in = np.max(np.abs(inp), axis=1)
        avr_t = stacks['time'].mean(axis=1)

        return delta_resp, avr_t, avr_in, max_in, max_thr

    def spectrum(self, time, traces):
        ### fouriertransform for noise analysis. returns frequencies and spectrum.
        pad = 1024 - (len(traces[0]) % 1024)  # padding to power of 2, increases transform speed
        traces = np.pad(traces, [[0, 0], [0, pad]], mode='constant')
        trspec = np.fft.rfft(traces, axis=-1, norm='ortho')
        trfreq = np.fft.rfftfreq(len(traces[0]), time[1] - time[0])
        return trfreq, trspec

    def stackfilter(self, time, trace_ref, trace_filt, window):
        ### calculates filter transmission and phaseshift from stack of windows. Not in use, maybe later.
        # slicing off last 2s to get rid of landing
        #maybe pass throttle for further analysis...
        filt = trace_filt[:-int(Trace.noise_superpos * 2. / Trace.noise_framelen), :] * window
        ref = trace_ref[:-int(Trace.noise_superpos * 2. / Trace.noise_framelen), :] * window
        time = time[:-int(Trace.noise_superpos * 2. / Trace.noise_framelen), :]

        full_freq_f, full_spec_f = self.spectrum(self.time, [self.data['gyro']])
        full_freq_r, full_spec_r = self.spectrum(self.time, [self.data['debug']])

        f_amp_freq, f_amp_hist =np.histogram(full_freq_f, weights=np.abs(full_spec_f.real).flatten(), bins=int(full_freq_f[-1]))
        r_amp_freq, r_amp_hist = np.histogram(full_freq_r, weights=np.abs(full_spec_r.real).flatten(), bins=int(full_freq_r[-1]))

    def hist2d(self, x, y, weights, bins):   #bins[nx,ny]
        ### generates a 2d hist from input 1d axis for x,y. repeats them to match shape of weights X*Y (data points)
        ### x will be 0-100%
        freqs = np.repeat(np.array([y], dtype=np.float64), len(x), axis=0)
        throts = np.repeat(np.array([x], dtype=np.float64), len(y), axis=0).transpose()
        throt_hist_avr, throt_scale_avr = np.histogram(x, 101, [0, 100])

        hist2d = np.histogram2d(throts.flatten(), freqs.flatten(),
                                range=[[0, 100], [y[0], y[-1]]],
                                bins=bins, weights=weights.flatten(), normed=False)[0].transpose()

        hist2d = np.array(abs(hist2d), dtype=np.float64)
        hist2d_norm = np.copy(hist2d)
        hist2d_norm /=  (throt_hist_avr + 1e-9)

        return {'hist2d_norm':hist2d_norm, 'hist2d':hist2d, 'throt_hist':throt_hist_avr,'throt_scale':throt_scale_avr}


    def stackspectrum(self, time, throttle, trace, window):
        ### calculates spectrogram from stack of windows against throttle.
        # slicing off last 2s to get rid of landing
        gyro = trace[:-int(Trace.noise_superpos*2./Trace.noise_framelen),:] * window
        thr = throttle[:-int(Trace.noise_superpos*2./Trace.noise_framelen),:] * window
        time = time[:-int(Trace.noise_superpos*2./Trace.noise_framelen),:]

        freq, spec = self.spectrum(time[0], gyro)

        weights = abs(spec.real)
        avr_thr = np.abs(thr).max(axis=1)

        hist2d=self.hist2d(avr_thr, freq,weights,[101,len(freq)/4])

        filt_width = 3  # width of gaussian smoothing for hist data
        hist2d_sm = gaussian_filter1d(hist2d['hist2d_norm'], filt_width, axis=1, mode='constant')

        # get max value in histogram >100hz
        thresh = 100.
        mask = self.to_mask(freq[:-1:4].clip(thresh-1e-9,thresh))
        maxval = np.max(hist2d_sm.transpose()*mask)

        return {'throt_hist_avr':hist2d['throt_hist'],'throt_axis':hist2d['throt_scale'],'freq_axis':freq[::4],
                'hist2d_norm':hist2d['hist2d_norm'], 'hist2d_sm':hist2d_sm, 'hist2d':hist2d['hist2d'], 'max':maxval}

    def weighted_mode_avr(self, values, weights, vertrange, vertbins):
        ### finds the most common trace and std
        threshold = 0.5  # threshold for std calculation
        filt_width = 7  # width of gaussian smoothing for hist data

        resp_y = np.linspace(vertrange[0], vertrange[-1], vertbins, dtype=np.float64)
        times = np.repeat(np.array([self.time_resp],dtype=np.float64), len(values), axis=0)
        weights = np.repeat(weights, len(values[0]))

        hist2d = np.histogram2d(times.flatten(), values.flatten(),
                                range=[[self.time_resp[0], self.time_resp[-1]], vertrange],
                                bins=[len(times[0]), vertbins], weights=weights.flatten())[0].transpose()
        ### shift outer edges by +-1e-5 (10us) bacause of dtype32. Otherwise different precisions lead to artefacting.
        ### solution to this --> somethings strage here. In outer most edges some bins are doubled, some are empty.
        ### Hence sometimes produces "divide by 0 error" in "/=" operation.

        if hist2d.sum():
            hist2d_sm = gaussian_filter1d(hist2d, filt_width, axis=0, mode='constant')
            hist2d_sm /= np.max(hist2d_sm, 0)


            pixelpos = np.repeat(resp_y.reshape(len(resp_y), 1), len(times[0]), axis=1)
            avr = np.average(pixelpos, 0, weights=hist2d_sm * hist2d_sm)
        else:
            hist2d_sm = hist2d
            avr = np.zeros_like(self.time_resp)
        # only used for monochrome error width
        hist2d[hist2d <= threshold] = 0.
        hist2d[hist2d > threshold] = 0.5 / (vertbins / (vertrange[-1] - vertrange[0]))

        std = np.sum(hist2d, 0)

        return avr, std, [self.time_resp, resp_y, hist2d_sm]

    ### calculates weighted avverage and resulting errors
    def weighted_avg_and_std(self, values, weights):
        average = np.average(values, axis=0, weights=weights)
        variance = np.average((values - average) ** 2, axis=0, weights=weights)
        return (average, np.sqrt(variance))


def plot_pid_response(trace, data, plot_config, label='Rate'):
    """Plot PID response for one axis

    :param trace: Trace object
    :param data: ULog.data_list
    """

    def _color_palette(hue, N=20):
        """ Color palette for the 2D histogram """
        saturation = 0.75
        vmin = 0.5
        def sat(i, N, s):
            """ get saturation: s if i < N/2, otherwise linearly increase
            in range [s, 1] """
            if i * 2 < N: return s
            return s + (i-N/2) / (N/2) * (1-s)
        hsv_tuples = [(hue, sat(N/2-x, N, saturation), vmin + x*(1-vmin)/N) for x in reversed(range(N))]
        colors = []
        alpha_max = 0.5
        delta_alpha = alpha_max / N
        alpha = 0
        for rgb in hsv_tuples:
            rgb = list(map(lambda x: int(x*255), colorsys.hsv_to_rgb(*rgb)))
            colors.append('rgba({:.0f},{:.0f},{:.0f},{:.3f})'.format(rgb[0], rgb[1], rgb[2], alpha))
            alpha += delta_alpha
        return colors


    data_plot = DataPlot(data, plot_config, 'sensor_combined',
                         y_axis_label='strength', x_axis_label='[s]',
                         title='Step Response for {:} {:}'.format(trace.name.capitalize(), label),
                         x_range=Range1d(0, trace.resplen),
                         y_range=Range1d(0, 2))
    p = data_plot.bokeh_plot

    color_mapper = LinearColorMapper(palette=_color_palette(0.55), low=0, high=1)
    image = trace.resp_low[2][2] # 2D histogram
    # y start and range comes from weighted_mode_avr(, , [-1.5, 3.5])
    p.image([image], x=0, y=-1.5, dw=trace.resplen, dh=5, color_mapper=color_mapper)

    has_high_rates = trace.high_mask.sum() > 0
    low_rates_label = ''
    if has_high_rates:
        low_rates_label = ' (<500 deg/s)'

    p.line(x=trace.time_resp, y=trace.resp_low[0],
           legend_label=trace.name.capitalize() + low_rates_label,
           line_width=4, line_color=colors3[2])

# Plotting a marker for the response time (first crossing of 1) looks nice, but
# does not necessarily mean much: on the same vehicle with the same gains, the
# (average) response time might be higher in one flight compared to another, if
# one of the flights contains generally lower rate setpoint jumps (e.g. when
# flying in acro vs. stabilized).
#    # find & mark first crossing of 1
#    response_time_idx = np.argmax(trace.resp_low[0] > 1)
#    if response_time_idx > 0:
#        # linearly interpolate to get a more accurate time
#        t = [trace.time_resp[response_time_idx-1], trace.time_resp[response_time_idx]]
#        y = [trace.resp_low[0][response_time_idx-1]-1, trace.resp_low[0][response_time_idx]-1]
#        response_time = t[0] - y[0] * (t[0]-t[1]) / (y[0]-y[1])
#        if response_time < 0.2: # only mark if it's sensible
#            response_line = Span(location=response_time,
#                                 dimension='height', line_color=colors3[2],
#                                 line_dash='dashed', line_width=2)
#            p.add_layout(response_line)
#
#            y_values = [20]
#            # add a space to separate it from the line
#            names = [' {:.0f} ms'.format(response_time*1000)]
#            source = ColumnDataSource(data=dict(x=np.array([response_time]),
#                                                names=names, y=y_values))
#            # plot as text with a fixed screen-space y offset
#            labels = LabelSet(x='x', y='y', text='names',
#                              y_units='screen', level='glyph',
#                              text_color=colors3[2],
#                              source=source, render_mode='canvas')
#            p.add_layout(labels)


    if has_high_rates:
        color_mapper = LinearColorMapper(palette=_color_palette(0.95), low=0, high=1)
        image = trace.resp_high[2][2] # 2D histogram
        # y start and range comes from weighted_mode_avr(, , [-1.5, 3.5])
        p.image([image], x=0, y=-1.5, dw=trace.resplen, dh=5, color_mapper=color_mapper)

        p.line(x=trace.time_resp, y=trace.resp_high[0],
               legend_label=trace.name.capitalize() + ' (>500 deg/s)',
               line_width=4, line_color=colors3[0])

    # horizonal marker line at 1
    data_span = Span(location=1,
                     dimension='width', line_color='black',
                     line_alpha=0.5, line_width=1.5)
    p.add_layout(data_span)

    data_plot.set_use_time_formatter(False)
    data_plot.finalize()
    return data_plot

