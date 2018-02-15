"""
Tornado handler for the JSON public log list retrieval
"""
from __future__ import print_function
import json
import sqlite3
import os
import sys
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_db_filename
from db_entry import DBData, DBDataGenerated

#pylint: disable=relative-beyond-top-level
from .common import generate_db_data_from_log_file

#pylint: disable=abstract-method

class DBInfoHandler(tornado.web.RequestHandler):
    """ Get database info (JSON list of public logs) Tornado request handler """

    def get(self, *args, **kwargs):

        jsonlist = list()

        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()
        cur.execute('select Id, Date, Description, WindSpeed, Rating, VideoUrl '
                    'from Logs where Public = 1')
        # need to fetch all here, because we will do more SQL calls while
        # iterating (having multiple cursor's does not seem to work)
        db_tuples = cur.fetchall()
        for db_tuple in db_tuples:
            jsondict = dict()
            db_data = DBData()
            log_id = db_tuple[0]
            jsondict['log_id'] = log_id
            jsondict['log_date'] = db_tuple[1].strftime('%Y-%m-%d')
            db_data.description = db_tuple[2]
            db_data.feedback = ''
            db_data.type = ''
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]
            jsondict.update(db_data.to_json_dict())

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
                    continue
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

            jsondict.update(db_data_gen.to_json_dict())
            jsonlist.append(jsondict)

        cur.close()
        con.close()

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(jsonlist))

