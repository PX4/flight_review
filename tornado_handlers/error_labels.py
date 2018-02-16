"""
Tornado handler for updating the error label information in the database
"""
from __future__ import print_function
import sys
import os
from html import escape
import sqlite3
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from config import *
from db_entry import *
from helper import validate_log_id, validate_error_labels_and_get_ids

class UpdateErrorLabelHandler(tornado.web.RequestHandler):
    """ Update the error label of a flight log."""

    def post(self, *args, **kwargs):

        log_id = escape(self.get_argument('log'))
        if not validate_log_id(log_id):
            raise tornado.web.HTTPError(400, 'Invalid Parameter')

        text_error_labels = escape(self.get_argument('labels')).split(',')[:-1]

        try:
            error_ids = validate_error_labels_and_get_ids(text_error_labels)
        except:
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
