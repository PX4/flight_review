""" Class for statistics plots page """
import functools
import re
import sqlite3

import numpy as np

from bokeh.plotting import figure
from bokeh.charts import Area
from bokeh.palettes import viridis # alternatives: magma, inferno
import bokeh.core.properties as props
from bokeh.models import (
    DatetimeTickFormatter, FixedTicker, FuncTickFormatter,
    HoverTool, ColumnDataSource
    )

from plotting import TOOLS, ACTIVE_SCROLL_TOOLS
from config import get_db_filename
from helper import get_airframe_data, flight_modes_table


#pylint: disable=too-few-public-methods,invalid-name,unused-argument,consider-using-enumerate
#pylint: disable=unsubscriptable-object

class _VersionData(object):
    """
    class that contains various information for a single version
    """
    def __init__(self):
        self.boards = {} # flight durations per board
        self.airframes = {} # flight durations per airframes
        self.airframes_num_logs = {} # num logs/flights per airframes
        self.ratings = {}
        self.flight_mode_durations = {} # flight durations per flight mode

class _Log(object):
    """
    container class containing a DB entry for one log
    """

    re_version_extract = re.compile(r'v([0-9]+)\.([0-9]+)\.?([0-9]*)')

    def __init__(self, db_tuple):
        self.log_id = db_tuple[0]
        self.date = db_tuple[1]
        self.source = db_tuple[2]
        self.is_public = db_tuple[3]
        self.rating = db_tuple[4]

        self.duration = 0
        self.autostart_id = 0
        self.hardware = ""
        self.uuid = ""
        self.sw_version = ""
        self.flight_mode_durations = []

    def set_generated(self, db_tuple):
        """ set from a LogsGenerated DB tuple """
        self.duration = db_tuple[1]
        self.autostart_id = db_tuple[4]
        self.hardware = db_tuple[5]
        self.uuid = db_tuple[11]
        # the version has typically the form 'v<i>.<j>.<k> <l>', where <l>
        # indicates whether it's a development version (most of the time it's 0)
        self.sw_version = db_tuple[10].split(' ')[0]

        self.flight_mode_durations = \
            [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]


    @staticmethod
    def compare_version(ver_a, ver_b):
        """
        compare version strings
        """
        # if the version is not set, it should be last
        if ver_a == '': return 1
        if ver_b == '': return -1
        versions = [ver_a, ver_b]
        version_tuples = []

        for version in versions:
            m = _Log.re_version_extract.match(version)
            if m:
                patch = 0
                if len(m.groups()) == 3:
                    patch = m.group(3)
                version_tuples.append((m.group(1), m.group(2), patch))
        if len(version_tuples) != 2:
            return -1

        for i in range(3):
            if version_tuples[0][i] < version_tuples[1][i]:
                return -1
            elif version_tuples[0][i] > version_tuples[1][i]:
                return 1
        return 0


class StatisticsPlots(object):
    """
    Class to generate statistics plots from Database entries
    """

    def __init__(self, plot_config, verbose_output=False):

        self._config = plot_config

        self._verbose_output = verbose_output

        # lists of dates when a _log was uploaded, one list per type
        self._public_logs_dates = []
        self._web_ui_logs_dates = []
        self._qgc_logs_dates = [] # private uploads via QGC
        self._ci_logs_dates = []
        self._all_logs_dates = []

        self._public_logs = []

        # read from the DB
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        with con:
            cur = con.cursor()

            cur.execute('select Id, Date, Source, Public, Rating from Logs')

            db_tuples = cur.fetchall()
            for db_tuple in db_tuples:
                log = _Log(db_tuple)

                self._all_logs_dates.append(log.date)
                if log.is_public == 1:
                    self._public_logs_dates.append(log.date)
                else:
                    if log.source == 'CI':
                        self._ci_logs_dates.append(log.date)
                    elif log.source == 'QGroundControl':
                        self._qgc_logs_dates.append(log.date)
                    else:
                        self._web_ui_logs_dates.append(log.date)


                # LogsGenerated: public only
                if log.is_public != 1:
                    continue

                cur.execute('select * from LogsGenerated where Id = ?', [log.log_id])
                db_tuple = cur.fetchone()

                if db_tuple is None:
                    print("Error: no generated data")
                    continue

                log.set_generated(db_tuple)

                # filter bogus entries
                if log.sw_version == 'v0.0.0':
                    if self._verbose_output:
                        print('Warning: %s with version=v0.0.0' % log.log_id)
                    continue

                if log.sw_version == '':
                    # FIXME: does that still occur and if so why?
                    if self._verbose_output:
                        print('Warning: %s version not set' % log.log_id)
                    continue

                if log.autostart_id == 0:
                    print('Warning: %s with autostart_id=0' % log.log_id)
                    continue

                self._public_logs.append(log)


        self._version_data = {} # dict of _VersionData items
        self._all_airframes = set()
        self._all_boards = set()
        self._all_ratings = set()
        self._all_flight_modes = set()
        self._total_duration = 0 # in hours, public logs only

        for log in self._public_logs:
            if not log.sw_version in self._version_data:
                self._version_data[log.sw_version] = _VersionData()

            self._all_airframes.add(str(log.autostart_id))
            self._all_boards.add(log.hardware)
            self._all_ratings.add(log.rating)

            cur_version_data = self._version_data[log.sw_version]
            boards = cur_version_data.boards
            airframes = cur_version_data.airframes
            airframes_num_logs = cur_version_data.airframes_num_logs
            ratings = cur_version_data.ratings
            flight_modes = cur_version_data.flight_mode_durations

            if not log.hardware in boards:
                boards[log.hardware] = 0
            boards[log.hardware] += log.duration / 3600.

            for flight_mode, duration in log.flight_mode_durations:
                flight_mode_str = str(flight_mode)
                self._all_flight_modes.add(flight_mode_str)
                if not flight_mode_str in flight_modes:
                    flight_modes[flight_mode_str] = 0.
                flight_modes[flight_mode_str] += duration / 3600.

            autostart_str = str(log.autostart_id)
            if not autostart_str in airframes:
                airframes[autostart_str] = 0
                airframes_num_logs[autostart_str] = 0
            airframes[autostart_str] += log.duration / 3600.
            airframes_num_logs[autostart_str] += 1

            if not log.rating in ratings:
                ratings[log.rating] = 0
            ratings[log.rating] += 1

            self._total_duration += log.duration / 3600.


    def plot_log_upload_statistics(self, colors):
        """
        plot upload statistics for different upload types. Each type is a list of
        datetime of a single upload
        :param colors: list of 5 colors
        :return: bokeh plot
        """
        title = 'Number of Log Files on the Server'
        p = figure(title=title, x_axis_label=None,
                   y_axis_label=None, tools=TOOLS,
                   active_scroll=ACTIVE_SCROLL_TOOLS)

        def plot_dates(p, dates_list, legend, color):
            """ plot a single line from a list of dates """
            counts = np.arange(1, len(dates_list)+1)

            # subsample
            dates_list_subsampled = []
            counts_subsampled = []
            previous_timestamp = 0
            for date, count in zip(dates_list, counts):
                t = int(date.timestamp()/(3600*4)) # use a granularity of 4 hours
                if t != previous_timestamp:
                    previous_timestamp = t
                    dates_list_subsampled.append(date)
                    counts_subsampled.append(count)

            p.line(dates_list_subsampled, counts_subsampled,
                   legend=legend, line_width=2, line_color=color)

        plot_dates(p, self._all_logs_dates, 'Total', colors[0])
        plot_dates(p, self._ci_logs_dates, 'Continuous Integration (Simulation Tests)', colors[1])
        plot_dates(p, self._web_ui_logs_dates, 'Private (via Web UI)', colors[2])
        plot_dates(p, self._qgc_logs_dates, 'Private (via QGC)', colors[3])
        plot_dates(p, self._public_logs_dates, 'Public', colors[4])

        p.xaxis.formatter = DatetimeTickFormatter(
            hours=["%d %b %Y %H:%M"],
            days=["%d %b %Y"],
            months=["%d %b %Y"],
            years=["%d %b %Y"],
            )
        self._setup_plot(p, 'large')

        return p

    def total_public_flight_duration(self):
        """ get total public flight hours """
        return self._total_duration


    def plot_public_boards_statistics(self):
        """
        plot board flight hour statistics for each version, for public logs
        :return: bokeh plot
        """

        return self._plot_public_data_statistics(
            self._all_boards, 'boards', 'Board', lambda x, short: x)


    def plot_public_airframe_statistics(self):
        """
        plot airframe flight hour statistics for each version, for public logs
        :return: bokeh plot
        """

        def label_callback(airframe_id, short):
            """ get the airframe label for the sys_autostart id """
            if short:
                return airframe_id
            airframe_data = get_airframe_data(airframe_id)
            if airframe_data is None:
                airframe_label = airframe_id
            else:
                airframe_type = ''
                if 'type' in airframe_data:
                    airframe_type = ', '+airframe_data['type']
                airframe_label = airframe_data.get('name')+ \
                                   airframe_type+' ('+airframe_id+')'
            return airframe_label

        return self._plot_public_data_statistics(
            self._all_airframes, 'airframes', 'Airframe', label_callback)

    def plot_public_flight_mode_statistics(self):
        """
        plot flight mode statistics for each version, for public logs
        :return: bokeh plot
        """

        def label_callback(flight_mode, short):
            """ get flight mode as string from an integer value """
            try:
                return flight_modes_table[int(flight_mode)][0]
            except:
                return 'Unknown'

        return self._plot_public_data_statistics(
            self._all_flight_modes, 'flight_mode_durations', 'Flight Mode', label_callback)

    def _plot_public_data_statistics(self, all_data, version_attr_name,
                                     title_name, label_cb):
        """
        generic method to plot flight hours one data type
        :param all_data: list with all types as string
        :param version_attr_name: attribute name of _VersionData
        :param title_name: name of the data for the title (and hover tool)
        :param label_cb: callback to create the label
        :return: bokeh plot
        """

        # change data structure
        data_hours = {} # key=data id, value=list of hours for each version
        for d in all_data:
            data_hours[d] = []

        versions = [] # sorted list of all versions
        for ver in sorted(self._version_data, key=functools.cmp_to_key(_Log.compare_version)):
            versions.append(ver)

            # all data points of the requested type for this version
            version_type_data = getattr(self._version_data[ver],
                                        version_attr_name)

            for d in all_data:
                if not d in version_type_data:
                    version_type_data[d] = 0.
                data_hours[d].append(version_type_data[d])


        # cumulative over each version
        for key in all_data:
            data_hours[key] = np.array(data_hours[key])
            data_hours[key+"_cum"] = np.cumsum(data_hours[key])


        # create a 2D numpy array. We could directly pass the dict to the bokeh
        # plot, but then we don't have control over the sorting order
        X = np.zeros((len(all_data), len(versions)))
        i = 0
        all_data_sorted = []
        for key in sorted(all_data, key=lambda data_key: data_hours[data_key+"_cum"][-1]):
            X[i, :] = data_hours[key+"_cum"]
            all_data_sorted.append(key)
            i += 1
        all_data = all_data_sorted


        colors = viridis(len(all_data))
        # alternative: use patches: http://bokeh.pydata.org/en/latest/docs/gallery/brewer.html
        area = Area(X, title="Flight Hours per "+title_name, tools=TOOLS,
                    active_scroll=ACTIVE_SCROLL_TOOLS,
                    stack=True, xlabel='version (including development states)',
                    ylabel='', color=colors)

        # now set the labels
        for i in range(len(all_data)):
            area.legend[0].items[i].label = props.value(label_cb(all_data[i], False))
        area.legend[0].items.reverse()

        # stack the data: we'll need it for the hover tool
        last = np.zeros(len(versions))
        for i in range(len(all_data)):
            last = last + X[i, :]
            data_hours[all_data[i]+'_stacked'] = last
        data_hours['x'] = np.arange(len(versions))

        # hover tool
        source = ColumnDataSource(data=data_hours)
        for d in all_data:
            renderer = area.circle(x='x', y=d+'_stacked', source=source,
                                   size=10, alpha=0, name=d)
            g1_hover = HoverTool(
                renderers=[renderer],
                tooltips=[(title_name, label_cb(d, True)),
                          ('Flight hours (only this version)', '@'+d+'{0,0.0}'),
                          ('Flight hours (up to this version)', '@'+d+'_cum{0,0.0}')])
            area.add_tools(g1_hover)


        # TODO: space x-axis entries according to version release date?
        area.xaxis.formatter = FuncTickFormatter(code="""
            var versions = """ + str(versions) + """;
            return versions[Math.floor(tick)]
        """)
        area.xaxis.ticker = FixedTicker(ticks=list(range(len(versions))))
        self._setup_plot(area)
        return area


    def _setup_plot(self, p, plot_height='normal'):
        """ apply layout options to a bokeh plot """

        plots_width = self._config['plot_width']
        plots_height = self._config['plot_height'][plot_height]
        p.plot_width = plots_width
        p.plot_height = plots_height

        p.xgrid.grid_line_color = 'navy'
        p.xgrid.grid_line_alpha = 0.13
        p.ygrid.grid_line_color = 'navy'
        p.ygrid.grid_line_alpha = 0.13
        p.legend.location = "top_left"
        p.toolbar.logo = None

