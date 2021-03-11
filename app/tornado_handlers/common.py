"""
Common methods and classes used by several tornado handlers
"""

from __future__ import print_function
import os
import sqlite3
import sys

from jinja2 import Environment, FileSystemLoader
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from db_entry import DBDataGenerated
from config import get_db_filename

#pylint: disable=abstract-method

_ENV = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app/templates')))

def get_jinja_env():
    """ get the jinja2 Environment object """
    return _ENV


class CustomHTTPError(tornado.web.HTTPError):
    """ simple class for HTTP exceptions with a custom error message """
    def __init__(self, status_code, error_message=None):
        self.error_message = error_message
        super().__init__(status_code, error_message)

class TornadoRequestHandlerBase(tornado.web.RequestHandler):
    """
    base class for a tornado request handler with custom error display
    """
    def write_error(self, status_code, **kwargs):
        html_template = """
<html><title>Error {status_code}</title>
<body>HTTP Error {status_code}{error_message}</body>
</html>
"""
        error_message = ''
        if 'exc_info' in kwargs:
            e = kwargs["exc_info"][1]
            if isinstance(e, CustomHTTPError) and e.error_message:
                error_message = ': '+e.error_message
        self.write(html_template.format(status_code=status_code,
                                        error_message=error_message))

def generate_db_data_from_log_file(log_id, db_connection=None):
    """
    Extract necessary information from the log file and insert as an entry to
    the LogsGenerated table (faster information retrieval later on).
    This is an expensive operation.
    It's ok to call this a second time for the same log, the call will just
    silently fail (but still read the whole log and will not update the DB entry)

    :return: DBDataGenerated object
    """

    db_data_gen = DBDataGenerated.from_log_file(log_id)

    need_closing = False
    if db_connection is None:
        db_connection = sqlite3.connect(get_db_filename())
        need_closing = True

    db_cursor = db_connection.cursor()
    try:
        db_cursor.execute(
            'insert into LogsGenerated (Id, Duration, '
            'Mavtype, Estimator, AutostartId, Hardware, '
            'Software, NumLoggedErrors, NumLoggedWarnings, '
            'FlightModes, SoftwareVersion, UUID, FlightModeDurations, StartTime) values '
            '(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [log_id, db_data_gen.duration_s, db_data_gen.mav_type,
             db_data_gen.estimator, db_data_gen.sys_autostart_id,
             db_data_gen.sys_hw, db_data_gen.ver_sw,
             db_data_gen.num_logged_errors,
             db_data_gen.num_logged_warnings,
             ','.join(map(str, db_data_gen.flight_modes)),
             db_data_gen.ver_sw_release, db_data_gen.vehicle_uuid,
             db_data_gen.flight_mode_durations_str(),
             db_data_gen.start_time_utc])
        db_connection.commit()
    except sqlite3.IntegrityError:
        # someone else already inserted it (race). just ignore it
        pass

    db_cursor.close()
    if need_closing:
        db_connection.close()

    return db_data_gen


def get_generated_db_data_from_log(log_id, con, cur):
    """
    try to get the additional data from the DB (or generate it if it does not
    exist)
    :param con: db connection
    :param cur: db cursor
    :return: DBDataGenerated or None
    """
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
            {int(x) for x in db_tuple[9].split(',') if len(x) > 0}
        db_data_gen.ver_sw_release = db_tuple[10]
        db_data_gen.vehicle_uuid = db_tuple[11]
        db_data_gen.flight_mode_durations = \
            [tuple(map(int, x.split(':'))) for x in db_tuple[12].split(',') if len(x) > 0]
    return db_data_gen

