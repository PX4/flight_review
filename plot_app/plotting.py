""" methods an classes used for plotting (wrappers around bokeh plots) """
from bokeh.plotting import figure
#pylint: disable=line-too-long, arguments-differ, unused-import
from bokeh.models import (
    ColumnDataSource, Range1d, DataRange1d, DatetimeAxis,
    TickFormatter, DatetimeTickFormatter, FuncTickFormatter,
    Grid, Legend, Plot, BoxAnnotation, Span, CustomJS, Rect, Circle, Line,
    HoverTool, BoxZoomTool, PanTool, WheelZoomTool,
    WMTSTileSource, GMapPlot, GMapOptions,
    LabelSet, Label, ColorBar, LinearColorMapper, BasicTicker, PrintfTickFormatter
    )
from bokeh.palettes import viridis
from bokeh.models.widgets import DataTable, DateFormatter, TableColumn

from downsampling import DynamicDownsample
import numpy as np
from scipy import signal
from helper import (
    map_projection, WGS84_to_mercator, flight_modes_table, vtol_modes_table
    )


TOOLS = "pan,wheel_zoom,box_zoom,reset,save"
ACTIVE_SCROLL_TOOLS = "wheel_zoom"


def plot_dropouts(p, dropouts, min_value, show_hover_tooltips=False):
    """ plot small rectangles with given min_value offset """

    if len(dropouts) == 0:
        return

    dropout_dict = {'left': [], 'right': [], 'top': [], 'bottom': [], 'duration' : []}
    for dropout in dropouts:
        d_start = dropout.timestamp
        d_end = dropout.timestamp + dropout.duration * 1000
        dropout_dict['left'].append(d_start)
        dropout_dict['right'].append(d_end)
        dropout_dict['top'].append(min_value + dropout.duration * 1000)
        dropout_dict['bottom'].append(min_value)
        dropout_dict['duration'].append(dropout.duration)

    source = ColumnDataSource(dropout_dict)
    quad = p.quad(left='left', right='right', top='top', bottom='bottom', source=source,
                  line_color='black', line_alpha=0.3, fill_color='black',
                  fill_alpha=0.15, legend='logging dropout')

    if show_hover_tooltips:
        p.add_tools(HoverTool(tooltips=[('dropout', '@duration ms')],
                              renderers=[quad]))


def plot_parameter_changes(p, plots_height, changed_parameters):
    """ plot changed parameters as text with value into bokeh plot p """
    timestamps = []
    names = []
    y_values = []
    i = 0
    for timestamp, name, value in changed_parameters:
        timestamps.append(timestamp)
        if isinstance(value, int):
            names.append('⦁ ' + name + ': {:}'.format(value))
        else:
            names.append('⦁ ' + name + ': {:.2f}'.format(value))
        # try to avoid overlapping text (TODO: do something more clever, dynamic?)
        y_values.append(plots_height - 50 - (i % 4) * 10)
        i += 1

    if len(names) > 0:
        source = ColumnDataSource(data=dict(x=timestamps, names=names, y=y_values))

        # plot as text with a fixed screen-space y offset
        labels = LabelSet(x='x', y='y', text='names',
                          y_units='screen', level='glyph', #text_alpha=0.9, text_color='black',
                          source=source, render_mode='canvas', text_font_size='8pt')
        p.add_layout(labels)
        return labels
    return None


def plot_flight_modes_background(p, flight_mode_changes, vtol_states=None):
    """ plot flight modes as filling background (with different colors) to bokeh
        plot p """
    vtol_state_height = 60
    added_box_annotation_args = {}
    if vtol_states is not None:
        added_box_annotation_args['bottom'] = vtol_state_height
        added_box_annotation_args['bottom_units'] = 'screen'
    for i in range(len(flight_mode_changes)-1):
        t_start, mode = flight_mode_changes[i]
        t_end, mode_next = flight_mode_changes[i + 1]
        if mode in flight_modes_table:
            mode_name, color = flight_modes_table[mode]
            p.add_layout(BoxAnnotation(left=int(t_start), right=int(t_end),
                                       fill_alpha=0.09, line_color=None,
                                       fill_color=color,
                                       **added_box_annotation_args))
    if vtol_states is not None:
        for i in range(len(vtol_states)-1):
            t_start, mode = vtol_states[i]
            t_end, mode_next = vtol_states[i + 1]
            if mode in vtol_modes_table:
                mode_name, color = vtol_modes_table[mode]
                p.add_layout(BoxAnnotation(left=int(t_start), right=int(t_end),
                                           fill_alpha=0.09, line_color=None,
                                           fill_color=color,
                                           top=vtol_state_height, top_units='screen'))
        # use screen coords so that the label always stays. It's a bit
        # unfortunate that the x position includes the x-offset of the y-axis,
        # which depends on the axis labels (e.g. 4.000e+5 creates a large offset)
        label = Label(x=83, y=32, x_units='screen', y_units='screen',
                      text='VTOL mode', text_font_size='10pt', level='glyph',
                      background_fill_color='white', background_fill_alpha=0.8)
        p.add_layout(label)


def plot_set_equal_aspect_ratio(p, x, y, zoom_out_factor=1.3, min_range=5):
    """
    Set plot range and make sure both plotting axis have an equal scaling.
    The plot size must already have been set before calling this.
    """
    x_range = [np.amin(x), np.amax(x)]
    x_diff = x_range[1]-x_range[0]
    if x_diff < min_range: x_diff = min_range
    x_center = (x_range[0]+x_range[1])/2
    y_range = [np.amin(y), np.amax(y)]
    y_diff = y_range[1]-y_range[0]
    if y_diff < min_range: y_diff = min_range
    y_center = (y_range[0]+y_range[1])/2

    # keep same aspect ratio as the plot
    aspect = p.plot_width / p.plot_height
    if aspect > x_diff / y_diff:
        x_diff = y_diff * aspect
    else:
        y_diff = x_diff / aspect

    p.x_range = Range1d(start=x_center - x_diff/2 * zoom_out_factor,
                        end=x_center + x_diff/2 * zoom_out_factor, bounds=None)
    p.y_range = Range1d(start=y_center - y_diff/2 * zoom_out_factor,
                        end=y_center + y_diff/2 * zoom_out_factor, bounds=None)

    p.select_one(BoxZoomTool).match_aspect = True




# GPS map

def plot_map(ulog, config, map_type='plain', api_key=None, setpoints=False,
             bokeh_plot=None):
    """
    Do a 2D position plot

    :param map_type: one of 'osm', 'google', 'plain'
    :param bokeh_plot: if None, create a new bokeh plot, otherwise use the
                       supplied one (only for 'plain' map_type)

    :return: bokeh plot object
    """

    try:
        cur_dataset = ulog.get_dataset('vehicle_gps_position')
        t = cur_dataset.data['timestamp']
        indices = cur_dataset.data['fix_type'] > 2 # use only data with a fix
        t = t[indices]
        lon = cur_dataset.data['lon'][indices] / 1e7 # degrees
        lat = cur_dataset.data['lat'][indices] / 1e7
        altitude = cur_dataset.data['alt'][indices] / 1e3 # meters

        plots_width = config['plot_width']
        plots_height = config['plot_height']['large']
        anchor_lat = 0
        anchor_lon = 0

        if len(t) == 0:
            raise ValueError('No valid GPS position data')


        if map_type == 'google':
            data_source = ColumnDataSource(data=dict(lat=lat, lon=lon))

            lon_center = (np.amin(lon) + np.amax(lon)) / 2
            lat_center = (np.amin(lat) + np.amax(lat)) / 2

            map_options = GMapOptions(lat=lat_center, lng=lon_center,
                                      map_type="hybrid", zoom=19)
            # possible map types: satellite, roadmap, terrain, hybrid

            p = GMapPlot(
                x_range=DataRange1d(), y_range=DataRange1d(), map_options=map_options,
                api_key=api_key, plot_width=plots_width, plot_height=plots_height
            )

            pan = PanTool()
            wheel_zoom = WheelZoomTool()
            p.add_tools(pan, wheel_zoom)
            p.toolbar.active_scroll = wheel_zoom

            line = Line(x="lon", y="lat", line_width=2, line_color=config['maps_line_color'])
            p.add_glyph(data_source, line)

        elif map_type == 'osm':

            # OpenStreetMaps

            # transform coordinates
            lon, lat = WGS84_to_mercator(lon, lat)
            data_source = ColumnDataSource(data=dict(lat=lat, lon=lon))

            p = figure(tools=TOOLS, active_scroll=ACTIVE_SCROLL_TOOLS)
            p.plot_width = plots_width
            p.plot_height = plots_height

            plot_set_equal_aspect_ratio(p, lon, lat)

            p.background_fill_color = "lightgray"
            p.axis.visible = False

            tile_options = {}
            # thunderforest
            tile_options['url'] = 'http://b.tile.thunderforest.com/landscape/{z}/{x}/{y}.png'
            tile_options['attribution'] = 'Maps © <a href="http://www.thunderforest.com">Thunderforest</a>, Data © <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '

            # default OpenStreetMaps
#            tile_options['url'] = 'http://c.tile.openstreetmap.org/{Z}/{X}/{Y}.png'
#            tile_options['attribution'] = '© <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors '

            # FIXME: tiles disabled for now due to a rendering bug
#            tile_source = WMTSTileSource(**tile_options)
#            tile_renderer_options = {}
#            p.add_tile(tile_source, **tile_renderer_options)

            # stamen (black & white)
#            STAMEN_TONER = WMTSTileSource(
#                url='http://tile.stamen.com/toner/{Z}/{X}/{Y}.png',
#                attribution=(
#                    'Map tiles by <a href="http://stamen.com">Stamen Design</a>, '
#                    'under <a href="http://creativecommons.org/licenses/by/3.0">CC BY 3.0</a>.'
#                    'Data by <a href="http://openstreetmap.org">OpenStreetMap</a>, '
#                    'under <a href="http://www.openstreetmap.org/copyright">ODbL</a>'
#                )
#            )
#            p.add_tile(STAMEN_TONER)

            p.line(x='lon', y='lat', source=data_source, line_width=2,
                   line_color=config['maps_line_color'])

        else: # plain

            # transform coordinates
            lat = np.deg2rad(lat)
            lon = np.deg2rad(lon)
            anchor_lat = lat[0]
            anchor_lon = lon[0]

            # try to get the anchor position from the dataset
            try:
                local_pos_data = ulog.get_dataset('vehicle_local_position')
                indices = np.nonzero(local_pos_data.data['ref_timestamp'])
                if len(indices[0]) > 0:
                    anchor_lat = np.deg2rad(local_pos_data.data['ref_lat'][indices[0][0]])
                    anchor_lon = np.deg2rad(local_pos_data.data['ref_lon'][indices[0][0]])
            except:
                pass


            lat, lon = map_projection(lat, lon, anchor_lat, anchor_lon)
            data_source = ColumnDataSource(data=dict(lat=lat, lon=lon))

            if bokeh_plot is None:
                p = figure(tools=TOOLS, active_scroll=ACTIVE_SCROLL_TOOLS,
                           x_axis_label='[m]', y_axis_label='[m]')
                p.plot_width = plots_width
                p.plot_height = plots_height

                plot_set_equal_aspect_ratio(p, lon, lat)
            else:
                p = bokeh_plot

            # TODO: altitude line coloring
            p.line(x='lon', y='lat', source=data_source, line_width=2,
                   line_color=config['maps_line_color'], legend='GPS (projected)')


        if setpoints:
            # draw (mission) setpoint as circles
            try:
                cur_dataset = ulog.get_dataset('position_setpoint_triplet')
                lon = cur_dataset.data['current.lon'] # degrees
                lat = cur_dataset.data['current.lat']

                if map_type == 'osm':
                    lon, lat = WGS84_to_mercator(lon, lat)
                elif map_type == 'plain':
                    lat = np.deg2rad(lat)
                    lon = np.deg2rad(lon)
                    lat, lon = map_projection(lat, lon, anchor_lat, anchor_lon)

                data_source = ColumnDataSource(data=dict(lat=lat, lon=lon))

                p.circle(x='lon', y='lat', source=data_source,
                         line_width=2, size=6, line_color=config['mission_setpoint_color'],
                         fill_color=None, legend='Position Setpoints')
            except:
                pass

    except (KeyError, IndexError, ValueError) as error:
        # log does not contain the value we are looking for
        print(type(error), "(vehicle_gps_position):", error)
        return None
    p.toolbar.logo = None
    return p


class DataPlot:
    """
    Handle the bokeh plot generation from an ULog dataset
    """


    def __init__(self, data, config, data_name, x_axis_label=None,
                 y_axis_label=None, title=None, plot_height='normal',
                 y_range=None, y_start=None, changed_params=None,
                 topic_instance=0, x_range=None):

        self._had_error = False
        self._previous_success = False
        self._param_change_label = None

        self._data = data
        self._config = config
        self._plot_height_name = plot_height
        self._data_name = data_name
        self._cur_dataset = None
        try:
            self._p = figure(title=title, x_axis_label=x_axis_label,
                             y_axis_label=y_axis_label, tools=TOOLS,
                             active_scroll=ACTIVE_SCROLL_TOOLS)
            if y_range is not None:
                self._p.y_range = Range1d(y_range.start, y_range.end)
            if x_range is not None:
                # we need a copy, otherwise x-axis zooming will be synchronized
                # between all plots
                self._p.x_range = Range1d(x_range.start, x_range.end)

            if changed_params is not None:
                self._param_change_label = \
                    plot_parameter_changes(self._p, config['plot_height'][plot_height],
                                           changed_params)

            self._cur_dataset = [elem for elem in data
                                 if elem.name == data_name and elem.multi_id == topic_instance][0]

            if y_start is not None:
                # make sure y axis starts at y_start. We do it by adding an invisible circle
                self._p.circle(x=int(self._cur_dataset.data['timestamp'][0]),
                               y=y_start, size=0, alpha=0)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True

    @property
    def title(self):
        """ return the bokeh title """
        if self._p is not None:
            return self._p.title.text
        else:
            return None

    @property
    def bokeh_plot(self):
        """ return the bokeh plot """
        return self._p

    @property
    def param_change_label(self):
        """ returns bokeh LabelSet or None """
        return self._param_change_label

    @property
    def had_error(self):
        """ Returns true if the previous plotting calls had an error (e.g. due
        to missing data in the log) """
        return self._had_error


    @property
    def dataset(self):
        """ get current dataset """
        return self._cur_dataset

    def change_dataset(self, data_name, topic_instance=0):
        """ select a new dataset. Afterwards, call add_graph etc """
        self._data_name = data_name
        if not self._had_error: self._previous_success = True
        self._had_error = False
        try:
            self._cur_dataset = [elem for elem in self._data
                                 if elem.name == data_name and elem.multi_id == topic_instance][0]
        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True
            self._cur_dataset = None


    def add_graph(self, field_names, colors, legends, use_downsample=True, mark_nan=False):
        """ add 1 or more lines to a graph

        field_names can be a list of fields from the data set, or a list of
        functions with the data set as argument and returning a tuple of
        (field_name, data)
        :param mark_nan: if True, add an indicator to the plot when one of the graphs is NaN
        """
        if self._had_error: return
        try:
            p = self._p
            data_set = {}
            data_set['timestamp'] = self._cur_dataset.data['timestamp']
            field_names_expanded = self._expand_field_names(field_names, data_set)

            if mark_nan:
                # look through the data to find NaN's and store their timestamps
                nan_timestamps = set()
                for key in field_names_expanded:
                    nan_indexes = np.argwhere(np.isnan(data_set[key]))
                    last_index = -2
                    for ind in nan_indexes:
                        if last_index + 1 != ind: # store only timestamps at the start of NaN
                            nan_timestamps.add(data_set['timestamp'][ind][0])
                        last_index = ind

                nan_color = 'black'
                for nan_timestamp in nan_timestamps:
                    nan_line = Span(location=nan_timestamp,
                                    dimension='height', line_color=nan_color,
                                    line_dash='dashed', line_width=3)
                    p.add_layout(nan_line)
                if len(nan_timestamps) > 0:
                    y_values = [30] * len(nan_timestamps)
                    names = ['NaN'] * len(nan_timestamps)
                    source = ColumnDataSource(data=dict(x=np.array(list(nan_timestamps))+1e5,
                                                        names=names, y=y_values))
                    # plot as text with a fixed screen-space y offset
                    labels = LabelSet(x='x', y='y', text='names',
                                      y_units='screen', level='glyph', text_color=nan_color,
                                      source=source, render_mode='canvas')
                    p.add_layout(labels)


            if use_downsample:
                # we directly pass the data_set, downsample and then create the
                # ColumnDataSource object, which is much faster than
                # first creating ColumnDataSource, and then downsample
                downsample = DynamicDownsample(p, data_set, 'timestamp')
                data_source = downsample.data_source
            else:
                data_source = ColumnDataSource(data=data_set)

            for field_name, color, legend in zip(field_names_expanded, colors, legends):
                p.line(x='timestamp', y=field_name, source=data_source,
                       legend=legend, line_width=2, line_color=color)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True

    def add_circle(self, field_names, colors, legends):
        """ add circles

        see add_graph for arguments description
        """
        if self._had_error: return
        try:
            p = self._p
            data_set = {}
            data_set['timestamp'] = self._cur_dataset.data['timestamp']
            field_names_expanded = self._expand_field_names(field_names, data_set)
            data_source = ColumnDataSource(data=data_set)

            for field_name, color, legend in zip(field_names_expanded, colors, legends):
                p.circle(x='timestamp', y=field_name, source=data_source,
                         legend=legend, line_width=2, size=6, line_color=color,
                         fill_color=None)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True


    def _expand_field_names(self, field_names, data_set):
        """
        expand field names if they're a function
        """
        field_names_expanded = []
        for field_name in field_names:
            if hasattr(field_name, '__call__'):
                new_field_name, new_data = field_name(self._cur_dataset.data)
                data_set[new_field_name] = new_data
                field_names_expanded.append(new_field_name)
            else:
                data_set[field_name] = self._cur_dataset.data[field_name]
                field_names_expanded.append(field_name)
        return field_names_expanded


    def add_span(self, field_name, accumulator_func=np.mean,
                 line_color='black', line_alpha=0.5):
        """ Add a vertical line. Location is determined by accumulating a
        dataset """
        if self._had_error: return
        try:
            accumulated_data = accumulator_func(self._cur_dataset.data[field_name])
            data_span = Span(location=accumulated_data.item(),
                             dimension='width', line_color=line_color,
                             line_alpha=line_alpha, line_width=1)
            self._p.add_layout(data_span)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True


    def finalize(self):
        """ Call this after all plots are done. Returns the bokeh plot, or None
        on error """
        if self._had_error and not self._previous_success:
            return None
        self._setup_plot()
        return self._p


    def _setup_plot(self):
        plots_width = self._config['plot_width']
        plots_height = self._config['plot_height'][self._plot_height_name]
        p = self._p

        p.plot_width = plots_width
        p.plot_height = plots_height

        # -> other attributes are set via theme.yaml

        # disable x grid lines
        p.xgrid.grid_line_color = None

        p.ygrid.grid_line_color = 'navy'
        p.ygrid.grid_line_alpha = 0.13
        p.ygrid.minor_grid_line_color = 'navy'
        p.ygrid.minor_grid_line_alpha = 0.05

        p.toolbar.logo = None # hide the bokeh logo (we give credit at the
                            # bottom of the page)

        #p.lod_threshold=None # turn off level-of-detail

        # axis labels: format time
        p.xaxis[0].formatter = FuncTickFormatter(code='''
                    //func arguments: ticks, x_range
                    // assume us ticks
                    ms = Math.round(tick / 1000)
                    sec = Math.floor(ms / 1000)
                    minutes = Math.floor(sec / 60)
                    hours = Math.floor(minutes / 60)
                    ms = ms % 1000
                    sec = sec % 60
                    minutes = minutes % 60

                    function pad(num, size) {
                        var s = num+"";
                        while (s.length < size) s = "0" + s;
                        return s;
                    }

                    if (hours > 0) {
                        var ret_val = hours + ":" + pad(minutes, 2) + ":" + pad(sec,2)
                    } else {
                        var ret_val = minutes + ":" + pad(sec,2);
                    }
                    if (x_range.end - x_range.start < 4e6) {
                        ret_val = ret_val + "." + pad(ms, 3);
                    }
                    return ret_val;
                ''', args={'x_range' : p.x_range})

        # make it possible to hide graphs by clicking on the label
        p.legend.click_policy = "hide"


class DataPlot2D(DataPlot):
    """
    A 2D plot (without map)
    This does not do downsampling.
    """


    def __init__(self, data, config, data_name, x_axis_label=None,
                 y_axis_label=None, title=None, plot_height='normal',
                 equal_aspect=True):

        super(DataPlot2D, self).__init__(data, config, data_name,
                                         x_axis_label=x_axis_label,
                                         y_axis_label=y_axis_label,
                                         title=title, plot_height=plot_height)

        self._equal_aspect = equal_aspect
        self._is_first_graph = True

        self._p.plot_width = self._config['plot_width']
        self._p.plot_height = self._config['plot_height'][self._plot_height_name]


    def add_graph(self, dataset_x, dataset_y, color, legend, check_if_all_zero=False):
        """ add a line to the graph
        """
        if self._had_error: return
        try:
            p = self._p

            x = self._cur_dataset.data[dataset_x]
            y = self._cur_dataset.data[dataset_y]
            # FIXME: bokeh should be able to handle np.nan values properly, but
            # we still get a ValueError('Out of range float values are not JSON
            # compliant'), if x or y contains nan
            non_nan_indexes = np.logical_not(np.logical_or(np.isnan(x), np.isnan(y)))
            x = x[non_nan_indexes]
            y = y[non_nan_indexes]

            if check_if_all_zero:
                if np.count_nonzero(x) == 0 and np.count_nonzero(y) == 0:
                    raise ValueError()

            data_source = ColumnDataSource(data=dict(x=x, y=y))

            p.line(x="x", y="y", source=data_source, line_width=2,
                   line_color=color, legend=legend)

            if self._is_first_graph:
                self._is_first_graph = False
                if self._equal_aspect:
                    plot_set_equal_aspect_ratio(p, x, y)

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "("+self._data_name+"):", error)
            self._had_error = True


    def _setup_plot(self):
        p = self._p
        p.toolbar.logo = None


class DataPlotSpec(DataPlot):
    """
    A spectrogram plot.
    This does not do downsampling.
    """

    def __init__(self, data, config, data_name, x_axis_label=None,
                 y_axis_label=None, title=None, plot_height='small',
                 x_range=None, y_range=None, topic_instance=0):

        self._had_error = False
        self._previous_success = False
        self._param_change_label = None
        self._title = title
        self._x_axis_label = x_axis_label
        self._y_axis_label = y_axis_label

        self._data = data
        self._config = config
        self._data_name = data_name
        self._cur_dataset = None
        self._p = None
        self._x_range = x_range
        self._y_range = y_range

        try:
            self._cur_dataset = [elem for elem in data
                                 if elem.name == data_name and elem.multi_id == topic_instance][0]

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "(" + self._data_name + "):", error)
            self._had_error = True

        self._plot_width = self._config['plot_width']
        self._plot_height = self._config['plot_height'][plot_height]

    @property
    def title(self):
        """ return the bokeh title """
        return self._title

    @property
    def bokeh_plot(self):
        """ return the bokeh plot """
        return self._p

    def finalize(self):
        """ Call this after all plots are done. Returns the bokeh plot, or None
        on error """
        if self._had_error and not self._previous_success:
            return None

        self._setup_plot()
        return self._p

    def _setup_plot(self):
        p = self._p
        p.toolbar.logo = None

        p.plot_width = self._plot_width
        p.plot_height = self._plot_height

        # -> other attributes are set via theme.yaml

        # disable x grid lines
        p.xgrid.grid_line_color = None

        p.toolbar.logo = None  # hide the bokeh logo (we give credit at the
        # bottom of the page)

        # p.lod_threshold=None # turn off level-of-detail

        # p.xaxis[0].ticker = BasicTicker(desired_num_ticks = 13)

        # axis labels: format time
        p.xaxis[0].formatter = FuncTickFormatter(code='''
                            //func arguments: ticks, x_range
                            // assume us ticks
                            ms = Math.round(tick * 1000)
                            sec = Math.floor(ms / 1000)
                            minutes = Math.floor(sec / 60)
                            hours = Math.floor(minutes / 60)
                            ms = ms % 1000
                            sec = sec % 60
                            minutes = minutes % 60

                            function pad(num, size) {
                                var s = num+"";
                                while (s.length < size) s = "0" + s;
                                return s;
                            }

                            if (hours > 0) {
                                var ret_val = hours + ":" + pad(minutes, 2) + ":" + pad(sec,2)
                            } else {
                                var ret_val = minutes + ":" + pad(sec,2);
                            }
                            if (x_range.end - x_range.start < 4) {
                                ret_val = ret_val + "." + pad(ms, 3);
                            }
                            return ret_val;
                        ''', args={'x_range': p.x_range})

            # make it possible to hide graphs by clicking on the label
            # p.legend.click_policy = "hide"

    def add_graph(self, field_names, legends, window='hann',window_length=256, noverlap=128):
        """ add a spectrogram plot to the graph

        field_names: can be a list of fields from the data set, or a list of
        functions with the data set as argument and returning a tuple of
        (field_name, data)
        legends: description for the field_names that will appear in the title of the plot
        window: the type of window to use for the frequency analysis. check scipy documentation for available window types.
        window_length: length of the analysis window in samples.
        noverlap: number of overlapping samples between windows.
        """

        if self._had_error: return
        try:
            data_set = {}
            data_set['timestamp'] = self._cur_dataset.data['timestamp']

            # calculate the sampling frequency
            dt = ((data_set['timestamp'][-1] - data_set['timestamp'][0]) * 1.0e-6) / len(data_set['timestamp'])
            fs = int(1.0 / dt)

            t_rel = (self._cur_dataset.data['timestamp'] + self._cur_dataset.data['accelerometer_timestamp_relative'] -
                     self._cur_dataset.data['timestamp'][0]) / 1.0e6

            field_names_expanded = self._expand_field_names(field_names, data_set)

            # calculate the spectrogram
            psd = dict()
            for key in field_names_expanded:
                y = np.interp(np.arange(0, t_rel[-1], 1.0 / fs), t_rel, data_set[key])
                f, t, psd[key] = signal.spectrogram(y,fs=fs, window='hann', nperseg=256, noverlap=128, scaling='density')

            # sum all psd's
            key_it = iter(psd)
            sum_psd = psd[next(key_it)]
            for key in key_it:
                sum_psd += psd[key]

            # offset = int(((1024/2.0)/250.0)*1e6)
            # add start time as offset
            start_t=self._cur_dataset.data['timestamp'][0]/1.0e6
            t = t + start_t

            # remove box zoom tool, to add a customized version later
            str_box_zoom = "box_zoom"
            str_begin = TOOLS.find(str_box_zoom)
            if str_begin != -1:
                UPDATED_TOOLS = TOOLS[:str_begin] + TOOLS[(str_begin+len(str_box_zoom)+1):]
            else:
                UPDATED_TOOLS = TOOLS

            color_mapper = LinearColorMapper(palette=viridis(256), low=-80, high=0)

            im = [10 * np.log10(sum_psd)]
            title = self._title
            for legend in legends:
                title += " " + legend
            title += " [dB]"
            self._p = figure(title=title,plot_width=self._plot_width, plot_height=self._plot_height,
                                      y_range=(f[0], f[-1]),
                                      x_axis_label=self._x_axis_label,
                                      y_axis_label=self._y_axis_label, toolbar_location='above',
                                      tools=UPDATED_TOOLS, active_scroll=ACTIVE_SCROLL_TOOLS)
            if self._x_range is not None:
                # we need a copy, otherwise x-axis zooming will be synchronized
                # between all plots
                self._p.x_range = Range1d(self._x_range.start/1.0e6, self._x_range.end/1.0e6)
            self._p.image(image=im, x=t[0], y=f[0],dw=(t[-1]-t[0]), dh=(f[-1]-f[0]), color_mapper=color_mapper)
            color_bar = ColorBar(color_mapper=color_mapper,
                                 major_label_text_font_size="5pt",
                                 ticker=BasicTicker(desired_num_ticks=5),
                                 formatter=PrintfTickFormatter(format="%f"),
                                 label_standoff=6, border_line_color=None, location=(0, 0))
            self._p.add_layout(color_bar, 'right')
            # add plot zoom tool that only zooms in time axis
            self._p.add_tools(BoxZoomTool(dimensions="width"))

        except (KeyError, IndexError, ValueError) as error:
            print(type(error), "(" + self._data_name + "):", error)
            self._had_error = True