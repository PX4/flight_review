"""
Tornado handler for updating the error label information in the database
"""
from __future__ import print_function

import sys
import os
import sqlite3
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from config import *
from db_entry import *
from helper import validate_log_id, validate_error_ids

class UpdateErrorLabelHandler(tornado.web.RequestHandler):
    """ Update the error label of a flight log."""

    def post(self, *args, **kwargs):
        """ POST request """

        data = tornado.escape.json_decode(self.request.body)

        log_id = data['log']
        if not validate_log_id(log_id):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        error_ids = data['labels']
        if not validate_error_ids(error_ids):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        error_id_str = ""
        for error_ix, error_id in enumerate(error_ids):
            error_id_str += str(error_id)
            if error_ix < len(error_ids)-1:
                error_id_str += ","

        con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
        cur = con.cursor()

        cur.execute(
            'UPDATE Logs SET ErrorLabels = ? WHERE Id = ?',
            (error_id_str, log_id))

        con.commit()
        cur.close()
        con.close()

        self.write('OK')

    def data_received(self, chunk):
        """ called whenever new data is received """
        pass
