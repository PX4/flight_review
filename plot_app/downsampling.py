""" Class for server-side dynamic data downsampling """

from timeit import default_timer as timer
import numpy as np
from bokeh.models import ColumnDataSource
from helper import print_timing


class DynamicDownsample:
    """ server-side dynamic data downsampling of bokeh time series plots
        using numpy data sources.
        Initializes the plot with a fixed number of samples per pixel and then
        dynamically loads samples when zooming in or out based on density
        thresholds.
        Currently uses a very simple downsampling by picking every N-th sample
    """
    def __init__(self, bokeh_plot, data, x_key):
        """ Initialize and setup callback

        Args:
            bokeh_plot (bokeh.plotting.figure) : plot for downsampling
            data (dict) : data source of the plots, contains all samples. Arrays
                          are expected to be numpy
            x_key (str): key for x axis in data
        """
        self.bokeh_plot = bokeh_plot
        self.x_key = x_key
        self.data = data
        self.last_step_size = 1

        # parameters
        # minimum number of samples/pixel. Below that, we load new data
        self.min_density = 2
        # density on startup: density used for initializing the plot. The
        # smaller this is, the less data needs to be loaded on page load (this
        # must still be >= min_density).
        self.startup_density = 3
        # when loading new data, number of samples/pixel is set to this value
        self.init_density = 5
        # when loading new data, add a percentage of data on both sides
        self.range_margin = 0.2

        # create a copy of the initial data
        self.init_data = {}
        self.cur_data = {}
        for k in data:
            self.init_data[k] = data[k]
            self.cur_data[k] = data[k]

        # first downsampling
        self.downsample(self.cur_data, self.bokeh_plot.plot_width *
                        self.startup_density)
        self.data_source = ColumnDataSource(data=self.cur_data)

        # register the callbacks
        bokeh_plot.x_range.on_change('start', self.x_range_change_cb)
        bokeh_plot.x_range.on_change('end', self.x_range_change_cb)


    def x_range_change_cb(self, attr, old, new):
        """ bokeh server-side callback when plot x-range changes (zooming) """
        cb_start_time = timer()

        new_range = [self.bokeh_plot.x_range.start, self.bokeh_plot.x_range.end]
        if None in new_range:
            return
        plot_width = self.bokeh_plot.plot_width
        init_x = self.init_data[self.x_key]
        cur_x = self.cur_data[self.x_key]
        cur_range = [cur_x[0], cur_x[-1]]

        need_update = False
        if (new_range[0] < cur_range[0] and cur_range[0] > init_x[0]) or \
                (new_range[1] > cur_range[1] and cur_range[1] < init_x[-self.last_step_size]):
            need_update = True # zooming out / panning

        visible_points = ((new_range[0] < cur_x) & (cur_x < new_range[1])).sum()
        if visible_points / plot_width < self.min_density:
            visible_points_all_data = ((new_range[0] < init_x) & (init_x < new_range[1])).sum()
            if visible_points_all_data > visible_points:
                need_update = True
            # else: reached maximum zoom level

        if visible_points / plot_width > self.init_density * 3:
            # mostly a precaution, the panning case above catches most cases
            need_update = True

        if need_update:
            drange = new_range[1] - new_range[0]
            new_range[0] -= drange * self.range_margin
            new_range[1] += drange * self.range_margin
            num_data_points = plot_width * self.init_density * (1 + 2*self.range_margin)
            indices = np.logical_and(init_x > new_range[0], init_x < new_range[1])

            self.cur_data = {}
            for k in self.init_data:
                self.cur_data[k] = self.init_data[k][indices]

            # downsample
            self.downsample(self.cur_data, num_data_points)

            self.data_source.data = self.cur_data

            print_timing("Data update", cb_start_time)


    def downsample(self, data, max_num_data_points):
        """ downsampling with a given maximum number of samples """
        if len(data[self.x_key]) > max_num_data_points:
            step_size = int(len(data[self.x_key]) / max_num_data_points)
            self.last_step_size = step_size
            for k in data:
                data[k] = data[k][::step_size]


