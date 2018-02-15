"""
Tornado handler for the browse page
"""
from __future__ import print_function
import sys
import os
import json
import sqlite3
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_db_filename
from db_entry import DBData, DBDataGenerated
from helper import flight_modes_table, get_airframe_data, html_long_word_force_break

#pylint: disable=relative-beyond-top-level
from .common import get_jinja_env, generate_db_data_from_log_file

BROWSE_TEMPLATE = 'browse.html'

#pylint: disable=abstract-method

class BrowseDataRetrievalHandler(tornado.web.RequestHandler):
    """ Ajax data retrieval handler """

    def get(self, *args, **kwargs):
        search_str = self.get_argument('search[value]', '').lower()
        data_start = int(self.get_argument('start'))
        data_length = int(self.get_argument('length'))
        draw_counter = int(self.get_argument('draw'))

        json_output = dict()
        json_output['draw'] = draw_counter


        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()

        cur.execute('SELECT Id, Date, Description, WindSpeed, Rating, VideoUrl '
                    'FROM Logs WHERE Public = 1 ORDER BY Date DESC')


        def get_columns_from_tuple(db_tuple, counter):
            """ load the columns (list of strings) from a db_tuple
            """
            db_data = DBData()
            log_id = db_tuple[0]
            log_date = db_tuple[1].strftime('%Y-%m-%d')
            db_data.description = db_tuple[2]
            db_data.feedback = ''
            db_data.type = ''
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]

            # try to get the additional data from the DB
            cur.execute('select * from LogsGenerated where Id = ?', [log_id])
            db_tuple = cur.fetchone()
            if db_tuple is None: # need to generate from file
                try:
                    # Note that this is not necessary in most cases, as the entry is
                    # also generated after uploading (but with a timeout)
                    db_data_gen = generate_db_data_from_log_file(log_id, con)
                except Exception as e:
                    print('Failed to load log file: '+str(e))
                    return None
            else: # get it from the DB
                db_data_gen = DBDataGenerated()
                db_data_gen.duration_s = db_tuple[1]
                db_data_gen.mav_type = db_tuple[2]
                db_data_gen.estimator = db_tuple[3]
                db_data_gen.sys_autostart_id = db_tuple[4]
                db_data_gen.sys_hw = db_tuple[5]
                db_data_gen.ver_sw = db_tuple[6]
                db_data_gen.num_logged_errors = db_tuple[7]
                db_data_gen.num_logged_warnings = db_tuple[8]
                db_data_gen.flight_modes = \
                    set([int(x) for x in db_tuple[9].split(',') if len(x) > 0])
                db_data_gen.ver_sw_release = db_tuple[10]
                db_data_gen.vehicle_uuid = db_tuple[11]
                db_data_gen.flight_mode_durations = \
                    [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]

            # bring it into displayable form
            ver_sw = db_data_gen.ver_sw
            if len(ver_sw) > 10:
                ver_sw = ver_sw[:6]
            if len(db_data_gen.ver_sw_release) > 0:
                try:
                    release_split = db_data_gen.ver_sw_release.split()
                    release_type = int(release_split[1])
                    if release_type == 255: # it's a release
                        ver_sw = release_split[0]
                except:
                    pass
            airframe_data = get_airframe_data(db_data_gen.sys_autostart_id)
            if airframe_data is None:
                airframe = db_data_gen.sys_autostart_id
            else:
                airframe = airframe_data['name']

            flight_modes = ', '.join([flight_modes_table[x][0]
                                      for x in db_data_gen.flight_modes if x in
                                      flight_modes_table])

            m, s = divmod(db_data_gen.duration_s, 60)
            h, m = divmod(m, 60)
            duration_str = '{:d}:{:02d}:{:02d}'.format(h, m, s)

            # make sure to break long descriptions w/o spaces (otherwise they
            # mess up the layout)
            description = html_long_word_force_break(db_data.description)

            return [
                counter,
                '<a href="plot_app?log='+log_id+'">'+log_date+'</a>',
                description,
                db_data_gen.mav_type,
                airframe,
                db_data_gen.sys_hw,
                ver_sw,
                duration_str,
                db_data.rating_str(),
                db_data_gen.num_logged_errors,
                flight_modes
                ]

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
            counter = len(db_tuples) - data_start + 1
            for i in range(data_start, min(data_start + data_length, len(db_tuples))):
                counter -= 1

                columns = get_columns_from_tuple(db_tuples[i], counter)
                if columns is None:
                    continue

                json_output['data'].append(columns)
            filtered_counter = len(db_tuples)
        else:
            counter = len(db_tuples) + 1
            for db_tuple in db_tuples:
                counter -= 1

                columns = get_columns_from_tuple(db_tuple, counter)
                if columns is None:
                    continue

                if any([search_str in str(column).lower() for column in columns]):
                    if filtered_counter >= data_start and \
                        filtered_counter < data_start + data_length:
                        json_output['data'].append(columns)
                    filtered_counter += 1


        cur.close()
        con.close()

        json_output['recordsFiltered'] = filtered_counter

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(json_output))


class BrowseHandler(tornado.web.RequestHandler):
    """ Browse public log file Tornado request handler """

    def get(self, *args, **kwargs):
        template = get_jinja_env().get_template(BROWSE_TEMPLATE)
        self.write(template.render())
