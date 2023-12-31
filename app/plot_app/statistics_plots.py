""" Class for statistics plots page """
import sqlite3
import datetime
from dateutil.relativedelta import relativedelta

import numpy as np

from bokeh.plotting import figure
from bokeh.palettes import viridis # alternatives: magma, inferno
from bokeh.models import (
    DatetimeTickFormatter,
    HoverTool, ColumnDataSource, LabelSet
    )

from plotting import TOOLS, ACTIVE_SCROLL_TOOLS
from config import get_db_filename
from helper import get_airframe_data, flight_modes_table, get_sw_releases


#pylint: disable=invalid-name,consider-using-dict-items


class _Log:
    """
    container class containing a DB entry for one log
    """

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

        self.is_release = False

    def set_generated(self, db_tuple):
        """ set from a LogsGenerated DB tuple """
        self.duration = db_tuple[1]
        self.autostart_id = db_tuple[4]
        self.hardware = db_tuple[5]
        self.uuid = db_tuple[11]
        # the version has typically the form 'v<i>.<j>.<k> <l>', where <l>
        # indicates whether it's a development version (most of the time it's 0)
        version = db_tuple[10].split(' ')
        self.sw_version = version[0]
        self.is_release = len(version) > 1 and version[1] == '255'

        self.flight_mode_durations = \
            [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]


class StatisticsPlots:
    """
    Class to generate statistics plots from Database entries
    """

    def __init__(self, plot_config, verbose_output=False):

        self._config = plot_config

        self._verbose_output = verbose_output

        self._num_logs_total = 0
        self._num_logs_ci = 0
        self._num_flight_hours_total = 0

        self._public_logs = []

        # read from the DB
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        with con:
            cur = con.cursor()

            cur.execute("select count(Id) from Logs")
            db_tuple = cur.fetchone()
            if db_tuple is not None:
                self._num_logs_total = db_tuple[0]

            cur.execute("select count(Id) from Logs where Source = 'CI'")
            db_tuple = cur.fetchone()
            if db_tuple is not None:
                self._num_logs_ci = db_tuple[0]

            # Get all log dates of specific types within 6 hour intervals
            cur.execute('''
select
    Date,
    count(*) cnt,
    datetime((strftime('%s', Date) / (6 * 60 * 60)) * 6 * 60 * 60, 'unixepoch') new_date
from Logs
where Public = 1
group by new_date
order by new_date
''')
            self._public_log_dates_intervals = cur.fetchall()
            cur.execute('''
select
    Date,
    count(*) cnt,
    datetime((strftime('%s', Date) / (6 * 60 * 60)) * 6 * 60 * 60, 'unixepoch') new_date
from Logs
where Public = 0
group by new_date
order by new_date
''')
            self._private_log_dates_intervals = cur.fetchall()

            # Get all public logs within the last few months
            cur.execute("select Id, Date, Source, Public, Rating from Logs where Public = 1 "
                        "and Source != 'CI' and "
                        "Date > date('now', '-90 day') order by Date")
            db_tuples = cur.fetchall()
            for db_tuple in db_tuples:
                log = _Log(db_tuple)

                cur.execute('select * from LogsGenerated where Id = ?', [log.log_id])
                db_tuple = cur.fetchone()

                if db_tuple is None:
                    if self._verbose_output:
                        print("Error: no generated data")
                    continue

                log.set_generated(db_tuple)

                # filter bogus entries
                if log.sw_version == 'v0.0.0':
                    if self._verbose_output:
                        print('Warning: %s with version=v0.0.0' % log.log_id)
                    continue
                if log.duration > 7*24*3600: # probably bogus timestamp(s)
                    if self._verbose_output:
                        print('Warning: %s with very high duration %i' %
                              (log.log_id, log.duration))
                    continue

                if log.sw_version == '':
                    # FIXME: does that still occur and if so why?
                    if self._verbose_output:
                        print('Warning: %s version not set' % log.log_id)
                    continue

                if log.autostart_id == 0:
                    if self._verbose_output:
                        print('Warning: %s with autostart_id=0' % log.log_id)
                    continue

                try:
                    ver_major = int(log.sw_version[1:].split('.')[0])
                    if ver_major >= 3 or ver_major == 0:
                        if self._verbose_output:
                            print('Warning: %s with large/small version %s' %
                                  (log.log_id, log.sw_version))
                        continue
                except:
                    continue

                self._public_logs.append(log)
                self._num_flight_hours_total += log.duration

            self._num_flight_hours_total /= 3600


    def get_data_for_plotting(self, groups_value_getter, empty_value=0,
                              value_adder=lambda a, b: a+b):
        """
        Get some data in a form that it can be used for plotting
        :return: tuple of list(dates), dict(group, list(value)),
                 with len(list(dates)) == len(list(value))
        """
        interval = relativedelta(days=1)
        cur_interval_date = self._public_logs[0].date
        dates = [cur_interval_date]
        groups = {} # map with list of values for each group
        for log in self._public_logs:
            if log.date > cur_interval_date + interval:
                dates.append(log.date)
                for group in groups:
                    groups[group].append(empty_value)
                cur_interval_date = log.date
            groups_and_values = groups_value_getter(log)
            for group, value in groups_and_values:
                if group not in groups:
                    groups[group] = [empty_value] * len(dates)
                groups[group][-1] = value_adder(groups[group][-1], value)
        return dates, groups



    def num_logs_total(self):
        """ get the total number of logs on the server """
        return self._num_logs_total

    def num_logs_ci(self):
        """ get the total number of CI logs on the server """
        return self._num_logs_ci

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

        def plot_dates(p, data_points, last_date, legend, color):
            """ plot a single line from a list of dates """

            # subsample
            dates_list_subsampled = []
            counts_subsampled = []
            count_total = 0
            for date, count, _ in data_points:
                dates_list_subsampled.append(date)
                count_total += count
                counts_subsampled.append(count_total)

            if len(counts_subsampled) > 0:
                if dates_list_subsampled[-1] < last_date:
                    # make sure the plot line extends to the last date
                    counts_subsampled.append(counts_subsampled[-1])
                    dates_list_subsampled.append(last_date)

                p.line(dates_list_subsampled, counts_subsampled,
                       legend_label=legend, line_width=2, line_color=color)

        if len(self._public_log_dates_intervals) > 0:
            last_date = self._public_log_dates_intervals[-1][0]
            plot_dates(p, self._private_log_dates_intervals, last_date, 'Private', colors[2])
            plot_dates(p, self._public_log_dates_intervals, last_date, 'Public', colors[4])


        # show the release versions as text markers
        release_dict = {'dates': [], 'tags': [], 'y': [], 'y_offset': []}
        max_logs_dates = self._public_log_dates_intervals # defines range limits of the plot
        if len(max_logs_dates) > 0:
            first_date = max_logs_dates[0][0]
            y_max = max(sum(x[1] for x in max_logs_dates),
                        sum(x[1] for x in self._private_log_dates_intervals))
            y_pos = -y_max*0.08

            releases = get_sw_releases()
            if releases:
                y_offset = True
                for release in reversed(releases):
                    tag = release['tag_name']
                    release_date_str = release['published_at']
                    release_date = datetime.datetime.strptime(release_date_str,
                                                              "%Y-%m-%dT%H:%M:%SZ")
                    if release_date > first_date and not 'rc' in tag.lower() \
                        and not 'beta' in tag.lower():
                        release_dict['dates'].append(release_date)
                        release_dict['tags'].append(tag)
                        release_dict['y'].append(y_pos)
                        if y_offset:
                            release_dict['y_offset'].append(5)
                        else:
                            release_dict['y_offset'].append(-18)
                        y_offset = not y_offset

            if len(release_dict['dates']) > 0:
                source = ColumnDataSource(data=release_dict)
                x = p.scatter(x='dates', y='y', size=4, source=source, color='#000000')
                labels = LabelSet(x='dates', y='y',
                                  text='tags', level='glyph',
                                  x_offset=2, y_offset='y_offset', source=source,
                                  text_font_size="10pt")
                p.add_layout(labels)

        self._setup_plot(p, 'large')

        return p

    def total_public_flight_duration(self):
        """ get total public flight hours """
        return self._num_flight_hours_total

    def plot_public_airframe_statistics(self):
        """
        plot airframe flight hour statistics, for public logs
        :return: bokeh plot
        """

        def label_callback(airframe_id):
            """ get the airframe label for the sys_autostart id """
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

        dates, groups = self.get_data_for_plotting(lambda log: [(str(log.autostart_id), 1)])
        # Cumulative
        for group in groups:
            groups[group] = np.cumsum(groups[group])

        return self.plot_groups_as_stack(dates, groups, "Number of Flights", "Airframe",
                                         label_callback)

    def plot_public_flight_mode_statistics(self):
        """
        plot flight mode statistics, for public logs
        :return: bokeh plot
        """

        def label_callback(flight_mode):
            """ get flight mode as string from an integer value """
            try:
                return flight_modes_table[int(flight_mode)][0]
            except:
                return f'Unknown ({flight_mode})'

        dates, groups = self.get_data_for_plotting(
            lambda log: [(str(mode), duration/3600)
                         for mode, duration in log.flight_mode_durations])
        # Cumulative
        for group in groups:
            groups[group] = np.cumsum(groups[group])

        return self.plot_groups_as_stack(dates, groups, "Flight Hours", "Flight Mode",
                                         label_callback)

    def plot_public_board_flights_statistics(self):
        """
        plot per-board #logs statistics, for public logs
        :return: bokeh plot
        """

        dates, groups = self.get_data_for_plotting(lambda log: [(log.hardware, 1)])
        # Cumulative
        for group in groups:
            groups[group] = np.cumsum(groups[group])

        return self.plot_groups_as_stack(dates, groups, "Number of Flights", "Board")

    def plot_public_board_hours_statistics(self):
        """
        plot per-board flight hour statistics, for public logs
        :return: bokeh plot
        """

        dates, groups = self.get_data_for_plotting(
            lambda log: [(log.hardware, log.duration / 3600)])
        # Cumulative
        for group in groups:
            groups[group] = np.cumsum(groups[group])

        return self.plot_groups_as_stack(dates, groups, "Flight Hours", "Board")

    def plot_public_version_flights_statistics(self):
        """
        plot per-version #logs statistics, for public logs
        :return: bokeh plot
        """

        dates, groups = self.get_data_for_plotting(
            lambda log: [('Not a Release' if not log.is_release else log.sw_version, 1)])
        # Cumulative
        for group in groups:
            groups[group] = np.cumsum(groups[group])

        return self.plot_groups_as_stack(dates, groups, "Number of Flights", "Version")

    def plot_public_unique_boards_statistics(self):
        """
        plot per-board #unique-boards statistics, for public logs
        :return: bokeh plot
        """

        dates, groups = self.get_data_for_plotting(
            lambda log: [(log.hardware, log.uuid)], [], lambda a, b: a + [b])
        # Cumulative
        for group in groups:
            all_previous = set()
            for i, date_list in enumerate(groups[group]):
                all_previous.update(set(date_list))
                groups[group][i] = len(all_previous)

        return self.plot_groups_as_stack(dates, groups, "Number of Unique Boards", "Board Type")

    def plot_groups_as_stack(self, dates, groups, title_prefix, title_name,
                             label_callback=lambda label: label):
        """
        Plot a set of groups as a stack plot
        :param dates: list of dates
        :param groups: dict of groups, each is a list of values
        :param title_prefix: plot title prefix
        :param title_name: plot tile name
        :param label_callback: convert the group name to a label
        :return: bokeh plot
        """

        all_groups = sorted(groups.keys(), key=lambda group: groups[group][-1])

        # Limit number of groups
        max_num_groups = 20
        if len(all_groups) > max_num_groups:
            others = np.array(groups[all_groups[0]])
            for i in range(1, len(all_groups)-max_num_groups+1):
                others += groups[all_groups[i]]
            groups['__others__'] = others
            all_groups = ['__others__'] + all_groups[len(all_groups)-max_num_groups+1:]

        colors = []
        palette = list(viridis(10))
        while len(colors) < len(all_groups):
            colors.extend(palette[:len(all_groups)-len(colors)])

        area = figure(title=title_prefix+" per "+title_name, tools=TOOLS,
                      active_scroll=ACTIVE_SCROLL_TOOLS,
                      x_axis_type='datetime',
                      y_axis_label='')

        legend_labels = ['Others' if l == '__others__' else label_callback(l) for l in all_groups]

        # Directly use the displayed label as data keys. It's the easiest way to ensure the hover
        # tool shows the right label, with the slight risk of creating a collision if 2 labels are
        # equal
        displayed_groups = {}
        for i, legend_label in enumerate(legend_labels):
            displayed_groups[legend_label] = groups[all_groups[i]]

        displayed_groups['__dates__'] = dates
        source = ColumnDataSource(data=displayed_groups)
        area.varea_stack(legend_labels, x='__dates__', color=colors, source=source,
                         legend_label=legend_labels, alpha=0.8)

        tooltips = """
    <div>
        <div>
            <span style="font-size: 12px; color: #05ABFF;">$name:</span>
            <span style="font-size: 12px; color: #000;">@$name</span>
        </div>
    </div>
"""
        area.add_tools(HoverTool(tooltips=tooltips))

        if area.legend:
            area.legend[0].items.reverse()

            # decrease size a bit to fit all items
            area.legend.label_text_font_size = '8pt'
            area.legend.label_height = 8
            area.legend.glyph_height = 10

        self._setup_plot(area, 'large')
        return area

    def _setup_plot(self, p, plot_height='normal'):
        """ apply layout options to a bokeh plot """

        p.xaxis.formatter = DatetimeTickFormatter(
            hours=["%d %b %Y %H:%M"],
            days=["%d %b %Y"],
            months=["%d %b %Y"],
            years=["%d %b %Y"],
        )

        plots_width = self._config['plot_width']
        plots_height = self._config['plot_height'][plot_height]
        p.width = plots_width
        p.height = plots_height

        p.xgrid.grid_line_color = 'navy'
        p.xgrid.grid_line_alpha = 0.13
        p.ygrid.grid_line_color = 'navy'
        p.ygrid.grid_line_alpha = 0.13
        p.legend.location = "top_left"
        p.toolbar.logo = None

