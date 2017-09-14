#! /usr/bin/env python3

import os, glob
import argparse
import requests


def get_arguments():
    parser = argparse.ArgumentParser(description='Python script for downloading public logs from the PX4/flight_review database.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max-num', '-n', type=int, default=-1,
                        help='Maximum number of files to download that match the search criteria. set to -1 to download all files.')
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
    return parser.parse_args()


def main():
    args = get_arguments()

    try:
        # the db_info_api sends a json file with a list of all public database entries
        db_entries_list = requests.get(url=args.db_info_api).json()
    except:
        print("Server request failed.")
        raise

    if args.print_entries:
        # only print the json output
        print(db_entries_list)
    else:
        if not os.path.isdir(args.download_folder):
            print("creating download directory " + args.download_folder)
            os.makedirs(args.download_folder)
        # find already existing logs in download folder
        logfile_pattern = os.path.join(os.path.abspath(args.download_folder), "*.ulg")
        logfiles = glob.glob(os.path.join(os.getcwd(), logfile_pattern))
        logids = frozenset(os.path.splitext(os.path.basename(f))[0] for f in logfiles)

        # set number of files to download
        n_en = len(db_entries_list)
        if (args.max_num > 0):
            n_en = min(n_en, args.max_num)

        n_downloaded = 0
        n_skipped = 0
        for i in range(n_en):
            entry_id = db_entries_list[i]['log_id']
            if args.overwrite or entry_id not in logids:
                file_path = os.path.join(args.download_folder, entry_id + ".ulg")

                print('downloading {:}/{:} ({:})'.format(i + 1, n_en, entry_id))
                r = requests.get(url=args.download_api + "?log=" + entry_id, stream=True)
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                n_downloaded += 1
            else:
                n_skipped += 1

        print('{:} logs downloaded to {:}, {:} logs skipped (already downloaded)'.format(
            n_downloaded, args.download_folder, n_skipped))


if __name__ == '__main__':
    main()
