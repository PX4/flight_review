#! /usr/bin/env python3
""" Script to download public logs """

import os
import glob
import argparse
import json
import datetime
import sys
import time

import requests

from plot_app.config_tables import *

# Rate limiting settings
DEFAULT_DELAY_SECONDS = 6  # 10 requests/minute = 6 seconds between requests
DEFAULT_MAX_NUM = 10       # Safe default to prevent accidental bulk downloads
WARN_THRESHOLD = 100       # Warn user if downloading more than this many files


def get_arguments():
    """ Get parsed CLI arguments """
    parser = argparse.ArgumentParser(description='Python script for downloading public logs '
                                                 'from the PX4/flight_review database.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max-num', '-n', type=int, default=DEFAULT_MAX_NUM,
                        help='Maximum number of files to download that match the search criteria. '
                             'Use -1 to download all (requires confirmation for >100 files).')
    parser.add_argument('-d', '--download-folder', type=str, default="data/downloaded/",
                        help='The folder to store the downloaded logfiles.')
    parser.add_argument('--print', action='store_true', dest="print_entries",
                        help='Whether to only print (not download) the database entries.')
    parser.add_argument('--overwrite', action='store_true', default=False,
                        help='Whether to overwrite already existing files in download folder.')
    parser.add_argument('--db-info-api', type=str, default="https://review.px4.io/dbinfo",
                        help='The url at which the server provides the dbinfo API.')
    parser.add_argument('--download-api', type=str, default="https://review.px4.io/download",
                        help='The url at which the server provides the download API.')
    parser.add_argument('--mav-type', type=str, default=None, nargs='+',
                        help='Filter logs by mav type (case insensitive). Specifying multiple '
                             'mav types is possible. e.g. Quadrotor, Hexarotor')
    parser.add_argument('--flight-modes', type=str, default=None, nargs='+',
                        help='Filter logs by flight modes. If multiple are provided, the log must '
                             'contain all modes. e.g. Mission')
    parser.add_argument('--error-labels', default=None, nargs='+', type=str,
                        help='Filter logs by error labels. If multiple are provided, the log must '
                             'contain all labels. e.g. Vibration')
    parser.add_argument('--rating', default=None, type=str, nargs='+',
                        help='Filter logs by rating. e.g. Good')
    parser.add_argument('--uuid', default=None, type=str, nargs='+',
                        help='Filter logs by a particular vehicle uuid. e.g. 0123456789')
    parser.add_argument('--log-id', default=None, type=str, nargs='+',
                        help='Filter logs by a particular log id')
    parser.add_argument('--vehicle-name', default=None, type=str,
                        help='Filter logs by a particular vehicle name.')
    parser.add_argument('--airframe-name', default=None, type=str,
                        help='Filter logs by a particular airframe name. e.g. Generic Quadrotor X')
    parser.add_argument('--airframe-type', default=None, type=str,
                        help='Filter logs by a particular airframe type. e.g. Quadrotor X')
    parser.add_argument('--latest-per-vehicle', action='store_true', dest="latest_per_vehicle",
                        help='Download only the latest log (by date) for each ' \
                        'unique vehicle (uuid).')
    parser.add_argument('--source', default=None, type=str,
                        help='The source of the log upload. e.g. ["webui", "CI"]')
    parser.add_argument('--git-hash', default=None, type=str,
                        help='The git hash of the PX4 Firmware version.')
    parser.add_argument('--delay', type=float, default=DEFAULT_DELAY_SECONDS,
                        help='Delay in seconds between downloads to respect server rate limits.')
    parser.add_argument('--yes', '-y', action='store_true', default=False,
                        help='Skip confirmation prompt for large downloads.')
    return parser.parse_args()


def flight_modes_to_ids(flight_modes):
    """
    returns a list of mode ids for a list of mode labels
    """
    flight_ids = []
    for i,value in flight_modes_table.items():
        if value[0] in flight_modes:
            flight_ids.append(i)
    return flight_ids


def error_labels_to_ids(error_labels):
    """
    returns a list of error ids for a list of error labels
    """
    error_id_table = {label: id for id, label in error_labels_table.items()}
    error_ids = [error_id_table[error_label] for error_label in error_labels]
    return error_ids


def confirm_large_download(n_files):
    """
    Ask user to confirm large downloads
    """
    print(f"\n{'='*60}")
    print(f"WARNING: You are about to download {n_files} files.")
    print(f"{'='*60}")
    print("\nThe server has rate limits in place. Bulk downloading without")
    print("appropriate delays may result in your IP being blocked.")
    print("\nNetwork and storage costs for Flight Review are funded by the")
    print("Dronecode Foundation. If you find this service useful, please")
    print("consider supporting the project: https://www.dronecode.org/membership/")
    print(f"\nTo download more files, use: --max-num {n_files} --yes")

    response = input("\nContinue with download? [y/N]: ")
    return response.lower() in ['y', 'yes']


def download_with_retry(url, entry_id, max_retries=5):
    """
    Download a file with rate-limit-aware retry logic
    """
    for attempt in range(max_retries):
        try:
            request = requests.get(url=url + "?log=" + entry_id, stream=True, timeout=10*60)

            if request.status_code == 503:
                # Rate limited - back off exponentially
                wait_time = min(30 * (2 ** attempt), 300)  # Max 5 minutes
                retry_after = request.headers.get('Retry-After')
                if retry_after:
                    wait_time = int(retry_after)
                print(f'  Rate limited (503). Waiting {wait_time}s before retry...')
                time.sleep(wait_time)
                continue

            if request.status_code in [403, 444]:
                # IP has been blocked
                print(f'\n{"="*60}')
                print(f'ERROR: Your IP address has been blocked (HTTP {request.status_code}).')
                print('This may be due to excessive download requests.')
                print('\nIf you believe this is an error, please contact:')
                print('https://github.com/PX4/flight_review/issues')
                print(f'{"="*60}\n')
                sys.exit(1)

            if request.status_code == 404:
                print('  Log not found (404). Skipping.')
                return None

            if request.status_code != 200:
                print(f'  Unexpected status {request.status_code}. Retrying...')
                time.sleep(10)
                continue

            return request

        except requests.exceptions.ConnectionError:
            # Connection refused or reset - could be IP block (444 closes connection)
            if attempt == 0:
                print('  Connection failed. This may indicate your IP has been blocked.')
                print(f'  Retrying ({attempt + 1}/{max_retries})...')
            else:
                print(f'  Connection failed. Retrying ({attempt + 1}/{max_retries})...')
            time.sleep(10 * (attempt + 1))
        except requests.exceptions.Timeout:
            print(f'  Request timed out. Retrying ({attempt + 1}/{max_retries})...')
            time.sleep(10)
        except requests.exceptions.RequestException as ex:
            print(f'  Request failed: {ex}')
            time.sleep(10)

    print(f'  Failed after {max_retries} attempts. Skipping.')
    return None


def main():
    """ main script entry point """
    args = get_arguments()

    try:
        # the db_info_api sends a json file with a list of all public database entries
        print("Fetching database info...")
        db_entries_list = requests.get(url=args.db_info_api, timeout=5*60).json()
        print(f"Found {len(db_entries_list)} total public logs in database.")
    except:
        print("Server request failed.")
        raise

    if args.print_entries:
        # only print the json output without downloading logs
        print(json.dumps(db_entries_list, indent=4, sort_keys=True))

    else:
        if not os.path.isdir(args.download_folder): # returns true if path is an existing directory
            print("creating download directory " + args.download_folder)
            os.makedirs(args.download_folder)

        # find already existing logs in download folder
        logfile_pattern = os.path.join(os.path.abspath(args.download_folder), "*.ulg")
        logfiles = glob.glob(os.path.join(os.getcwd(), logfile_pattern))
        logids = frozenset(os.path.splitext(os.path.basename(f))[0] for f in logfiles)

        # filter for mav types
        if args.mav_type is not None:
            mav = [mav_type.lower() for mav_type in args.mav_type]
            db_entries_list = [entry for entry in db_entries_list
                               if entry["mav_type"].lower() in mav]

        # filter for rating
        if args.rating is not None:
            rate = [rating.lower() for rating in args.rating]
            db_entries_list = [entry for entry in db_entries_list
                               if entry["rating"].lower() in rate]

        # filter for error labels
        if args.error_labels is not None:
            err_labels = error_labels_to_ids(args.error_labels)
            db_entries_list = [entry for entry in db_entries_list
                               if set(err_labels).issubset(set(entry["error_labels"]))]
            # compares numbers, must contain all

        # filter for flight modes
        if args.flight_modes is not None:
            modes = flight_modes_to_ids(args.flight_modes)
            db_entries_list = [entry for entry in db_entries_list
                               if set(modes).issubset(set(entry["flight_modes"]))]
            # compares numbers, must contain all

        # filter for vehicle uuid
        if args.uuid is not None:
            db_entries_list = [
                entry for entry in db_entries_list if entry['vehicle_uuid'] in args.uuid]


        # filter log_id
        if args.log_id is not None:
            arg_log_ids_without_dashes = [log_id.replace("-", "") for log_id in args.log_id]
            db_entries_list = [
                entry for entry in db_entries_list
                if entry['log_id'].replace("-", "") in arg_log_ids_without_dashes]

        # filter for vehicle name
        if args.vehicle_name is not None:
            db_entries_list = [
                entry for entry in db_entries_list if entry['vehicle_name'] == args.vehicle_name]

        # filter for airframe name
        if args.airframe_name is not None:
            db_entries_list = [
                entry for entry in db_entries_list if entry['airframe_name'] == args.airframe_name]

        # filter for airframe type
        if args.airframe_type is not None:
            db_entries_list = [
                entry for entry in db_entries_list if entry['airframe_type'] == args.airframe_type]

        if args.latest_per_vehicle:
            # find latest log_date for all different vehicles
            uuids = {}
            for entry in db_entries_list:
                if 'vehicle_uuid' in entry:
                    uuid = entry['vehicle_uuid']
                    date = datetime.datetime.strptime(entry['log_date'], '%Y-%m-%d')
                    if uuid in uuids:
                        if date > uuids[uuid]:
                            uuids[uuid] = date
                    else:
                        uuids[uuid] = date
            # filter: use the latest log for each vehicle
            db_entries_list_filtered = []
            added_uuids = set()
            for entry in db_entries_list:
                if 'vehicle_uuid' in entry:
                    date = datetime.datetime.strptime(entry['log_date'], '%Y-%m-%d')
                    uuid = entry['vehicle_uuid']
                    if date == uuids[entry['vehicle_uuid']] and not uuid in added_uuids:
                        db_entries_list_filtered.append(entry)
                        added_uuids.add(uuid)
            db_entries_list = db_entries_list_filtered

        if args.source is not None:
            db_entries_list = [
                entry for entry in db_entries_list
                if 'source' in entry and entry['source'] == args.source]

        if args.git_hash is not None:
            db_entries_list = [
                entry for entry in db_entries_list if entry['ver_sw'] == args.git_hash]

        # sort list order to first download the newest log files
        db_entries_list = sorted(
            db_entries_list,
            key=lambda x: datetime.datetime.strptime(x['log_date'], '%Y-%m-%d'),
            reverse=True)

        # set number of files to download
        n_matched = len(db_entries_list)
        print(f"{n_matched} logs match your filter criteria.")

        if args.max_num > 0:
            n_en = min(n_matched, args.max_num)
            if n_matched > args.max_num:
                print(f"Limiting to {args.max_num} files (use --max-num to change).")
        else:
            n_en = n_matched

        # Warn for large downloads
        if n_en > WARN_THRESHOLD and not args.yes:
            if not confirm_large_download(n_en):
                print("Download cancelled.")
                sys.exit(0)

        n_downloaded = 0
        n_skipped = 0
        n_failed = 0

        for i in range(n_en):
            entry_id = db_entries_list[i]['log_id']

            if not args.overwrite and entry_id in logids:
                n_skipped += 1
                continue

            file_path = os.path.join(args.download_folder, entry_id + ".ulg")
            print('Downloading {}/{} ({})'.format(i + 1, n_en, entry_id))

            request = download_with_retry(args.download_api, entry_id)

            if request is None:
                n_failed += 1
                continue

            with open(file_path, 'wb') as log_file:
                for chunk in request.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        log_file.write(chunk)
            n_downloaded += 1

            # Rate limit delay between downloads (skip on last file)
            if i < n_en - 1:
                time.sleep(args.delay)

        print('\nDownload complete:')
        print(f'  {n_downloaded} logs downloaded to {args.download_folder}')
        print(f'  {n_skipped} logs skipped (already downloaded)')
        if n_failed > 0:
            print(f'  {n_failed} logs failed')


if __name__ == '__main__':
    main()
