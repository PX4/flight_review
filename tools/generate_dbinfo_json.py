#!/usr/bin/env python3
"""
Standalone script to generate the /dbinfo JSON file from the SQLite database.

Produces output identical to the /dbinfo Tornado endpoint but writes it to a
file instead of serving it over HTTP. Intended to run as a cron job, with the
output uploaded to S3 and served via CloudFront.

Usage:
    python3 generate_dbinfo_json.py /path/to/logs.sqlite /path/to/output.json

    # With download URLs pointing to a CDN:
    python3 generate_dbinfo_json.py /path/to/logs.sqlite /path/to/output.json \
        --download-url-prefix https://cdn.example.com/

    # Also write aggregate upload counts, including private and CI logs:
    python3 generate_dbinfo_json.py /path/to/logs.sqlite /path/to/output.json \
        --stats-output /path/to/dbinfo_stats.json
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree

# The app's own lookup tables, so consumers of the stats file decode fields
# exactly as Flight Review does. config_tables has no dependencies.
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             '..', 'app', 'plot_app'))
from config_tables import flight_modes_table  # pylint: disable=wrong-import-position

AIRFRAMES_URL = 'https://px4-travis.s3.amazonaws.com/Firmware/master/_general/airframes.xml'

# Firmware type byte in ver_sw_release ('v1.17.0 255'), as defined by pyulog's
# get_version_info: a value maps to the highest key that is <= it.
RELEASE_TYPES = {0: 'dev', 64: 'alpha', 128: 'beta', 192: 'rc', 255: 'release'}


def download_airframes_xml():
    """Download airframes.xml from PX4 S3 and parse into a dict mapping
    autostart_id -> {name, type}."""
    airframes = {}
    try:
        print('Downloading airframes.xml...')
        with tempfile.NamedTemporaryFile(suffix='.xml', delete=True) as tmp:
            urllib.request.urlretrieve(AIRFRAMES_URL, tmp.name)
            root = xml.etree.ElementTree.parse(tmp.name).getroot()
            for group in root.findall('airframe_group'):
                for airframe in group.findall('airframe'):
                    aid = airframe.get('id')
                    entry = {'name': airframe.get('name', '')}
                    type_elem = airframe.find('type')
                    if type_elem is not None and type_elem.text:
                        entry['type'] = type_elem.text
                    airframes[aid] = entry
        print('Loaded %d airframes' % len(airframes))
    except Exception as e:
        print('Warning: failed to download airframes.xml: %s' % e,
              file=sys.stderr)
        print('Airframe names will be empty')
    return airframes


def generate(db_path, airframes, download_url_prefix=''):
    """Query the database and return the JSON-serializable list."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Vehicle UUID -> name mapping
    cur.execute('SELECT UUID, Name FROM Vehicle')
    vehicle_table = {row[0]: row[1] for row in cur.fetchall()}

    # All public non-CI logs
    cur.execute(
        'SELECT Id, Date, Description, WindSpeed, Rating, VideoUrl, '
        'ErrorLabels, Source, Feedback, Type '
        'FROM Logs WHERE Public = 1 AND NOT Source = "CI"'
    )
    logs = cur.fetchall()

    jsonlist = []
    for row in logs:
        log_id = row[0]

        # Get generated data via a second query (same N+1 pattern as the
        # original handler — a JOIN would be faster but we want identical
        # output for now)
        cur.execute('SELECT * FROM LogsGenerated WHERE Id = ?', [log_id])
        gen = cur.fetchone()
        if gen is None:
            continue

        # Parse fields exactly as the app does
        error_labels = sorted(
            [int(x) for x in row[6].split(',') if len(x) > 0]
        ) if row[6] else []

        flight_modes = {int(x) for x in gen[9].split(',') if len(x) > 0}
        flight_mode_durations = [
            tuple(map(int, x.split(':')))
            for x in gen[12].split(',') if len(x) > 0
        ]

        vehicle_uuid = gen[11] if gen[11] else ''
        sys_autostart_id = int(gen[4]) if gen[4] else 0

        airframe_data = airframes.get(str(sys_autostart_id))
        airframe_name = airframe_data.get('name', '') if airframe_data else ''
        airframe_type = (
            airframe_data.get('type', sys_autostart_id)
            if airframe_data else sys_autostart_id
        )

        entry = {
            # From Logs table
            'log_id': log_id,
            'log_date': str(row[1])[:10],
            'description': row[2] if row[2] else '',
            'feedback': row[8] if row[8] else '',
            'type': row[9] if row[9] else 'personal',
            'wind_speed': row[3] if row[3] is not None else -1,
            'rating': row[4] if row[4] else '',
            'video_url': row[5] if row[5] else '',
            'error_labels': error_labels,
            'source': row[7] if row[7] else '',
            # From LogsGenerated table
            'duration_s': int(gen[1]) if gen[1] else 0,
            'mav_type': gen[2] if gen[2] else '',
            'estimator': gen[3] if gen[3] else '',
            'sys_autostart_id': sys_autostart_id,
            'sys_hw': gen[5] if gen[5] else '',
            'ver_sw': gen[6] if gen[6] else '',
            'ver_sw_release': gen[10] if gen[10] else '',
            'num_logged_errors': gen[7] if gen[7] else 0,
            'num_logged_warnings': gen[8] if gen[8] else 0,
            'flight_modes': list(flight_modes),
            'vehicle_uuid': vehicle_uuid,
            'flight_mode_durations': flight_mode_durations,
            # Derived
            'vehicle_name': vehicle_table.get(vehicle_uuid, ''),
            'airframe_name': airframe_name,
            'airframe_type': airframe_type,
        }

        if download_url_prefix:
            entry['download_url'] = download_url_prefix + log_id + '.ulg'

        jsonlist.append(entry)

    cur.close()
    con.close()
    return jsonlist


# Same split as the statistics page: CI uploads, then public vs private.
CATEGORY_SQL = ("CASE WHEN IFNULL(Source, '') = 'CI' THEN 'ci' "
                "WHEN Public = 1 THEN 'public' ELSE 'private' END")


def generate_stats(db_path):
    """Upload counts for all logs, including private and CI ones, which the
    dbinfo list leaves out. Counts only: no per-log data."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute('SELECT %s AS category, count(*), min(date(Date)) '
                'FROM Logs GROUP BY category' % CATEGORY_SQL)
    totals = {}
    retained_since = {}
    for category, count, first_day in cur.fetchall():
        totals[category] = count
        retained_since[category] = first_day

    cur.execute('SELECT date(Date) AS day, '
                "sum(IFNULL(Source, '') <> 'CI' AND Public = 1), "
                "sum(IFNULL(Source, '') <> 'CI' AND Public = 0), "
                "sum(IFNULL(Source, '') = 'CI') "
                'FROM Logs GROUP BY day ORDER BY day')
    daily = [{'day': day, 'public': public, 'private': private, 'ci': ci}
             for day, public, private, ci in cur.fetchall()]

    cur.execute('SELECT date(Date) AS day, Source, sum(Public = 1), sum(Public = 0) '
                "FROM Logs WHERE IFNULL(Source, '') <> 'CI' GROUP BY day, Source ORDER BY day, Source")
    daily_by_source = [{'day': day, 'source': source if source else '',
                        'public': public, 'private': private}
                       for day, source, public, private in cur.fetchall()]

    cur.close()
    con.close()
    return {
        'generated_at': datetime.datetime.now(datetime.timezone.utc)
                        .strftime('%Y-%m-%dT%H:%M:%SZ'),
        'retained_since': retained_since,
        'totals': totals,
        'daily': daily,
        'daily_by_source': daily_by_source,
        # Legends for decoding dbinfo.json entries
        'flight_modes': {str(mode): name for mode, (name, _color)
                         in sorted(flight_modes_table.items())},
        'release_types': {str(value): name for value, name in RELEASE_TYPES.items()},
    }


def write_json(path, data):
    """Write atomically: temp file then rename."""
    json_data = json.dumps(data)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(json_data)
    os.replace(tmp_path, path)
    print('Written %.1f MB to: %s' % (len(json_data) / (1024 * 1024), path))


def main():
    parser = argparse.ArgumentParser(
        description='Generate the /dbinfo JSON file from the SQLite database.')
    parser.add_argument('db_path', help='Path to the SQLite database')
    parser.add_argument('output_path', help='Path to write the JSON output')
    parser.add_argument('--download-url-prefix', default='',
                        help='URL prefix for direct log file downloads. '
                             'When set, each entry includes a download_url field. '
                             'Example: https://cdn.example.com/')
    parser.add_argument('--stats-output', default='',
                        help='Also write aggregate upload counts (public, private '
                             'and CI, per day and per source) to this path')
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print('Error: database not found: %s' % args.db_path, file=sys.stderr)
        sys.exit(1)

    airframes = download_airframes_xml()

    print('Querying database: %s' % args.db_path)
    jsonlist = generate(args.db_path, airframes, args.download_url_prefix)
    print('Generated %d entries' % len(jsonlist))
    write_json(args.output_path, jsonlist)

    if args.stats_output:
        write_json(args.stats_output, generate_stats(args.db_path))


if __name__ == '__main__':
    main()
