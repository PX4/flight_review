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
from helper import get_airframe_data


#pylint: disable=relative-beyond-top-level
from .common import get_generated_db_data_from_log

#pylint: disable=abstract-method

class DBInfoHandler(tornado.web.RequestHandler):
    """ Get database info (JSON list of public logs) Tornado request handler """

    def get(self, *args, **kwargs):
        """ GET request """

        jsonlist = list()

        # get the logs (but only the public ones)
        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()

        # get vehicle name information from vehicle table
        cur.execute('select UUID, Name from Vehicle')
        db_tuples = cur.fetchall()
        vehicle_table = {db_tuple[0]: db_tuple[1] for db_tuple in db_tuples}

        cur.execute('select Id, Date, Description, WindSpeed, Rating, VideoUrl, ErrorLabels, '
                    'Source, Feedback, Type from Logs where Public = 1')
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
            db_data.wind_speed = db_tuple[3]
            db_data.rating = db_tuple[4]
            db_data.video_url = db_tuple[5]
            db_data.error_labels = sorted([int(x) for x in db_tuple[6].split(',') if len(x) > 0]) \
                if db_tuple[6] else []
            db_data.source = db_tuple[7]
            db_data.feedback = db_tuple[8]
            db_data.type = db_tuple[9]
            jsondict.update(db_data.to_json_dict())

            db_data_gen = get_generated_db_data_from_log(log_id, con, cur)
            if db_data_gen is None:
                continue

            jsondict.update(db_data_gen.to_json_dict())
            # add vehicle name
            jsondict['vehicle_name'] = vehicle_table.get(jsondict['vehicle_uuid'], '')
            airframe_data = get_airframe_data(jsondict['sys_autostart_id'])
            jsondict['airframe_name'] = airframe_data.get('name', '') \
                if airframe_data is not None else ''
            jsondict['airframe_type'] = airframe_data.get('type', jsondict['sys_autostart_id']) \
                if airframe_data is not None else jsondict['sys_autostart_id']

            jsonlist.append(jsondict)

        cur.close()
        con.close()

        self.set_header('Content-Type', 'application/json')
        self.write(json.dumps(jsonlist))

