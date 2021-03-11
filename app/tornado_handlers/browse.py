"""
Tornado handler for the browse page
"""
from __future__ import print_function
import collections
import sys
import os
from datetime import datetime
import json
import sqlite3
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_db_filename, get_overview_img_filepath
from db_entry import DBData, DBDataGenerated
from helper import flight_modes_table, get_airframe_data, html_long_word_force_break

#pylint: disable=relative-beyond-top-level,too-many-statements
from .common import get_jinja_env, get_generated_db_data_from_log

BROWSE_TEMPLATE = 'browse.html'

#pylint: disable=abstract-method

class BrowseDataRetrievalHandler(tornado.web.RequestHandler):
    """ Ajax data retrieval handler """

    def get(self, *args, **kwargs):
        """ GET request """
        search_str = self.get_argument('search[value]', '').lower()
        order_ind = int(self.get_argument('order[0][column]'))
        order_dir = self.get_argument('order[0][dir]', '').lower()
        data_start = int(self.get_argument('start'))
        data_length = int(self.get_argument('length'))
        draw_counter = int(self.get_argument('draw'))

        json_output = dict()
        json_output['draw'] = draw_counter


        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()

        sql_order = ' ORDER BY Date DESC'

        ordering_col = ['',#table row number
                        'Logs.Date',
                        '',#Overview - img
                        'Logs.Description',
                        'LogsGenerated.MavType',
                        '',#Airframe - not from DB
                        'LogsGenerated.Hardware',
                        'LogsGenerated.Software',
                        'LogsGenerated.Duration',
                        'LogsGenerated.StartTime',
                        '',#Rating
                        'LogsGenerated.NumLoggedErrors',
                        '' #FlightModes
                        ]
        if ordering_col[order_ind] != '':
            sql_order = ' ORDER BY ' + ordering_col[order_ind]
            if order_dir == 'desc':
                sql_order += ' DESC'

        cur.execute('SELECT Logs.Id, Logs.Date, '
                    '       Logs.Description, Logs.WindSpeed, '
                    '       Logs.Rating, Logs.VideoUrl, '
                    '       LogsGenerated.* '
                    'FROM Logs '
                    '   LEFT JOIN LogsGenerated on Logs.Id=LogsGenerated.Id '
                    'WHERE Logs.Public = 1 AND NOT Logs.Source = "CI" '
                    +sql_order)

        # pylint: disable=invalid-name
        Columns = collections.namedtuple("Columns", "columns search_only_columns")

        def get_columns_from_tuple(db_tuple, counter):
            """ load the columns (list of strings) from a db_tuple
            """

            db_data = DBDataJoin()
            log_id = db_tuple[0]
            log_date = db_tuple[1].strftime('%Y-%m-%d')
            db_data.description = db_tuple[2]
            db_data.feedback = ''
            db_data.type = ''
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]
            generateddata_log_id = db_tuple[6]
            if log_id != generateddata_log_id:
                print('Join failed, loading and updating data')
                db_data_gen = get_generated_db_data_from_log(log_id, con, cur)
                if db_data_gen is None:
                    return None
                db_data.add_generated_db_data_from_log(db_data_gen)
            else:
                db_data.duration_s = db_tuple[7]
                db_data.mav_type = db_tuple[8]
                db_data.estimator = db_tuple[9]
                db_data.sys_autostart_id = db_tuple[10]
                db_data.sys_hw = db_tuple[11]
                db_data.ver_sw = db_tuple[12]
                db_data.num_logged_errors = db_tuple[13]
                db_data.num_logged_warnings = db_tuple[14]
                db_data.flight_modes = \
                    {int(x) for x in db_tuple[15].split(',') if len(x) > 0}
                db_data.ver_sw_release = db_tuple[16]
                db_data.vehicle_uuid = db_tuple[17]
                db_data.flight_mode_durations = \
                   [tuple(map(int, x.split(':'))) for x in db_tuple[18].split(',') if len(x) > 0]
                db_data.start_time_utc = db_tuple[19]

            # bring it into displayable form
            ver_sw = db_data.ver_sw
            if len(ver_sw) > 10:
                ver_sw = ver_sw[:6]
            if len(db_data.ver_sw_release) > 0:
                try:
                    release_split = db_data.ver_sw_release.split()
                    release_type = int(release_split[1])
                    if release_type == 255: # it's a release
                        ver_sw = release_split[0]
                except:
                    pass
            airframe_data = get_airframe_data(db_data.sys_autostart_id)
            if airframe_data is None:
                airframe = db_data.sys_autostart_id
            else:
                airframe = airframe_data['name']

            flight_modes = ', '.join([flight_modes_table[x][0]
                                      for x in db_data.flight_modes if x in
                                      flight_modes_table])

            m, s = divmod(db_data.duration_s, 60)
            h, m = divmod(m, 60)
            duration_str = '{:d}:{:02d}:{:02d}'.format(h, m, s)

            start_time_str = 'N/A'
            if db_data.start_time_utc != 0:
                start_datetime = datetime.fromtimestamp(db_data.start_time_utc)
                start_time_str = start_datetime.strftime("%Y-%m-%d  %H:%M")

            # make sure to break long descriptions w/o spaces (otherwise they
            # mess up the layout)
            description = html_long_word_force_break(db_data.description)

            search_only_columns = []

            if db_data.ver_sw is not None:
                search_only_columns.append(db_data.ver_sw)

            if db_data.ver_sw_release is not None:
                search_only_columns.append(db_data.ver_sw_release)

            if db_data.vehicle_uuid is not None:
                search_only_columns.append(db_data.vehicle_uuid)

            image_col = '<div class="no_map_overview"> Not rendered / No GPS </div>'
            image_filename = os.path.join(get_overview_img_filepath(), log_id+'.png')
            if os.path.exists(image_filename):
                image_col = '<img class="map_overview" src="/overview_img/'
                image_col += log_id+'.png" alt="Overview Image Load Failed" height=50/>'

            return Columns([
                counter,
                '<a href="plot_app?log='+log_id+'">'+log_date+'</a>',
                image_col,
                description,
                db_data.mav_type,
                airframe,
                db_data.sys_hw,
                ver_sw,
                duration_str,
                start_time_str,
                db_data.rating_str(),
                db_data.num_logged_errors,
                flight_modes
            ], search_only_columns)

        # need to fetch all here, because we will do more SQL calls while
        # iterating (having multiple cursor's does not seem to work)
        db_tuples = cur.fetchall()
        json_output['recordsTotal'] = len(db_tuples)
        json_output['data'] = []
        if data_length == -1:
            data_length = len(db_tuples)

        filtered_counter = 0
        if search_str == '':
            # speed-up the request by iterating only over the requested items
            counter = data_start
            for i in range(data_start, min(data_start + data_length, len(db_tuples))):
                counter += 1

                columns = get_columns_from_tuple(db_tuples[i], counter)
                if columns is None:
                    continue

                json_output['data'].append(columns.columns)
            filtered_counter = len(db_tuples)
        else:
            counter = 1
            for db_tuple in db_tuples:
                counter += 1

                columns = get_columns_from_tuple(db_tuple, counter)
                if columns is None:
                    continue

                if any(search_str in str(column).lower() for column in \
                        (columns.columns, columns.search_only_columns)):
                    if data_start <= filtered_counter < data_start + data_length:
                        json_output['data'].append(columns.columns)
                    filtered_counter += 1


        cur.close()
        con.close()

        json_output['recordsFiltered'] = filtered_counter

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(json_output))

class DBDataJoin(DBData, DBDataGenerated):
    """Class for joined Data"""

    def add_generated_db_data_from_log(self, source):
        """Update joined data by parent data"""
        self.__dict__.update(source.__dict__)


class BrowseHandler(tornado.web.RequestHandler):
    """ Browse public log file Tornado request handler """

    def get(self, *args, **kwargs):
        """ GET request """
        template = get_jinja_env().get_template(BROWSE_TEMPLATE)

        template_args = {}

        search_str = self.get_argument('search', '').lower()
        if len(search_str) > 0:
            template_args['initial_search'] = json.dumps(search_str)

        self.write(template.render(template_args))
