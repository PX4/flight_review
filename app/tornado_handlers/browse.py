"""
Tornado handler for the browse page
"""
from __future__ import print_function
import sys
import os
import re
from datetime import datetime
import json
import tornado.web

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../plot_app'))
from config import get_db_connection, get_overview_img_filepath
from db_entry import DBData, DBDataGenerated
from helper import flight_modes_table, get_airframe_data

#pylint: disable=relative-beyond-top-level,too-many-statements
from .common import get_jinja_env, get_generated_db_data_from_log

BROWSE_TEMPLATE = 'browse.html'

_TAG_PREFIX_RE = re.compile(
    r"""^v[0-9]+(?:\.[0-9]+){0,2}                   # vMAJOR[.MINOR[.PATCH]]
        (?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?     # optional -prerelease
        (?:\+[0-9A-Za-z.-]+)?                       # optional +build
     """,
    re.IGNORECASE | re.VERBOSE,
)

# columns searchable via SQL LIKE
_SEARCH_COLUMNS = [
    'Logs.Description',
    'LogsGenerated.MavType',
    'LogsGenerated.Hardware',
    'LogsGenerated.Software',
    'LogsGenerated.SoftwareVersion',
    'LogsGenerated.UUID',
]

_BASE_WHERE = 'Logs.Public = 1 AND NOT Logs.Source = ?'
_BASE_PARAMS = ['CI']

_SELECT_COLS = ('SELECT Logs.Id, Logs.Date, '
                '       Logs.Description, Logs.WindSpeed, '
                '       Logs.Rating, Logs.VideoUrl, '
                '       LogsGenerated.* '
                'FROM Logs '
                '   LEFT JOIN LogsGenerated on Logs.Id=LogsGenerated.Id ')

def format_duration(seconds: int) -> str:
    """ Format duration in seconds to HhMmSs string """
    try:
        seconds = int(seconds)
    except Exception:
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)

    if h: return f"{h}h{m}m{s}s"
    if m: return f"{m}m{s}s"
    return f"{s}s"


def _is_hashish(q: str) -> bool:
    """ return true if the string looks like a git hash """
    if len(q) < 4:
        return False
    hex_chars = set('0123456789abcdef')
    return all(c in hex_chars for c in q)

def _is_tagish(q: str) -> bool:
    """ return true if the string looks like a git tag """
    if not q or q[0] not in ('v', 'V'):
        return False
    return bool(_TAG_PREFIX_RE.match(q))


def _escape_like(s):
    """Escape LIKE wildcards so %, _ are matched literally."""
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

_MAX_PAGE_SIZE = 500

def _build_search_clause(search_str):
    """Build SQL WHERE clause and params for a search string.

    Returns (sql_fragment, params) where sql_fragment is like
    '(col1 LIKE ? ESCAPE '\\' OR col2 LIKE ? ESCAPE '\\' ...)'
    and params is a list of bound values.
    """
    if not search_str:
        return '', []

    escaped = _escape_like(search_str)
    like_expr = "LIKE ? ESCAPE '\\'"

    hash_mode = _is_hashish(search_str)
    tag_mode = _is_tagish(search_str)

    if hash_mode or tag_mode:
        # prefix match on software version columns only
        pattern = escaped + '%'
        prefix_cols = ['LogsGenerated.Software', 'LogsGenerated.SoftwareVersion']
        clauses = [f'{col} {like_expr}' for col in prefix_cols]
        # also allow substring match on remaining columns as fallback
        sub_pattern = '%' + escaped + '%'
        fallback_cols = [col for col in _SEARCH_COLUMNS if col not in prefix_cols]
        clauses += [f'{col} {like_expr}' for col in fallback_cols]
        params = [pattern] * len(prefix_cols) + [sub_pattern] * len(fallback_cols)
    else:
        pattern = '%' + escaped + '%'
        clauses = [f'{col} {like_expr}' for col in _SEARCH_COLUMNS]
        params = [pattern] * len(_SEARCH_COLUMNS)

    return '(' + ' OR '.join(clauses) + ')', params


def _get_columns_from_tuple(db_tuple, counter, all_overview_imgs, con, cur):
    """ load the display columns from a db_tuple """

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

    duration_str = format_duration(db_data.duration_s)

    start_time_str = 'N/A'
    if db_data.start_time_utc != 0:
        try:
            start_datetime = datetime.fromtimestamp(db_data.start_time_utc)
            start_time_str = start_datetime.strftime("%Y-%m-%d %H:%M")
        except ValueError as value_error:
            # bogus date
            print(value_error)

    rounded_div_class = "h-100 w-100 bg-body-secondary rounded overflow-hidden"
    image_col_class = "object-fit-cover d-block"
    overview_image_filename = f"{log_id}.png"
    if overview_image_filename in all_overview_imgs:
        image_col = f"""
            <div class="">
                <img class="map_overview {image_col_class}"
                    src="/overview_img/{overview_image_filename}"
                    loading="lazy" decoding="async" />
            </div>
        """
    else:
        image_col = f"""
            <div class="{rounded_div_class}" style="width:60px;">
                <div class="no_map_overview text-warning">
                    No Image Preview
                </div>
            </div>
        """

    return [
        counter,
        f'<a href="plot_app?log={log_id}">{log_date}</a>',
        image_col,
        db_data.mav_type,
        airframe,
        db_data.sys_hw,
        ver_sw,
        duration_str,
        start_time_str,
        flight_modes
    ]


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

        json_output = {'draw': draw_counter, 'data': []}

        con = get_db_connection()
        cur = con.cursor()

        # build ORDER BY — indices must match the DataTables columns config
        ordering_col = ['',                          # 0: row number
                        'Logs.Date',                 # 1: Uploaded
                        '',                          # 2: Overview (image)
                        'LogsGenerated.MavType',     # 3: Type
                        '',                          # 4: Airframe (not orderable)
                        'LogsGenerated.Hardware',    # 5: Hardware
                        'LogsGenerated.Software',    # 6: Software
                        'LogsGenerated.Duration',    # 7: Duration
                        'LogsGenerated.StartTime',   # 8: Start Time
                        '',                          # 9: Flight Modes (not orderable)
                        ]
        sql_order = ' ORDER BY Logs.Date DESC'
        if 0 <= order_ind < len(ordering_col) and ordering_col[order_ind] != '':
            col = ordering_col[order_ind]
            direction = ' DESC' if order_dir == 'desc' else ''
            # push NULLs to the end regardless of sort direction
            sql_order = f' ORDER BY {col} IS NULL, {col}{direction}'

        # build WHERE with optional search
        where = 'WHERE ' + _BASE_WHERE
        params = list(_BASE_PARAMS)

        search_clause, search_params = _build_search_clause(search_str)
        if search_clause:
            where += ' AND ' + search_clause
            params += search_params

        # total records (unfiltered)
        cur.execute('SELECT COUNT(*) FROM Logs WHERE ' + _BASE_WHERE, _BASE_PARAMS)
        json_output['recordsTotal'] = cur.fetchone()[0]

        # filtered count
        cur.execute('SELECT COUNT(*) FROM Logs '
                    'LEFT JOIN LogsGenerated on Logs.Id=LogsGenerated.Id '
                    + where, params)
        records_filtered = cur.fetchone()[0]
        json_output['recordsFiltered'] = records_filtered

        # fetch only the page we need, enforce a hard max to prevent
        # unbounded queries from reintroducing the performance problem
        if data_length <= 0 or data_length > _MAX_PAGE_SIZE:
            data_length = _MAX_PAGE_SIZE
        limit_clause = ' LIMIT ? OFFSET ?'
        params += [data_length, data_start]

        cur.execute(_SELECT_COLS + where + sql_order + limit_clause, params)
        db_tuples = cur.fetchall()

        all_overview_imgs = set(os.listdir(get_overview_img_filepath()))
        for i, db_tuple in enumerate(db_tuples):
            counter = data_start + i + 1
            columns = _get_columns_from_tuple(
                db_tuple, counter, all_overview_imgs, con, cur)
            if columns is not None:
                json_output['data'].append(columns)

        cur.close()
        con.close()

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
