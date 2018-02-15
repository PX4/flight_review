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
from db_entry import DBData

#pylint: disable=relative-beyond-top-level
from .common import get_generated_db_data_from_log

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

            db_data_gen = get_generated_db_data_from_log(log_id, con, cur)
            if db_data_gen is None:
                continue

            jsondict.update(db_data_gen.to_json_dict())
            jsonlist.append(jsondict)

        cur.close()
        con.close()

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(jsonlist))

