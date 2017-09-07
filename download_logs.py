!import os, glob
import argparse
import requests

def get_arguments():
    parser = argparse.ArgumentParser(description='Python script for downloading public logs from the PX4/flight_review database.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    def str2bool(v):
        if v.lower() in ('true', 't', 'y', '1'):
            return True
        elif v.lower() in ('false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')
    parser.add_argument('--n', type=int, default=10,
                        help='Maximum number of files to download that match the search criteria. set to -1 to download all files.')
    parser.add_argument('--download_folder', type=str, default="data/downloaded/",
                        help='The folder to store the downloaded logfiles.')
    parser.add_argument('--print', type=str2bool, nargs='?', const=True, default=False,
                        help='Whether to only print (not download) the database entries.')
    parser.add_argument('--overwrite', type=str2bool, nargs='?', const=True, default=False,
                        help='Whether to overwrite already existing files in download folder.')
    parser.add_argument('--db_info_api', type=str, default="http://review.px4.io/dbinfo",
                        help='The url at which the server provides the dbinfo API.')
    parser.add_argument('--download_api', type=str, default="http://review.px4.io/download",
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

    if args.print:
        # only print the json output
        print(db_entries_list)
    else:
        # find already existing logs in download folder
        logfile_pattern = os.path.abspath(args.download_folder) + "/*.ulg"
        logfiles = glob.glob(os.path.join(os.getcwd(), logfile_pattern))
        logids = frozenset(os.path.splitext(os.path.basename(f))[0] for f in logfiles)

        # set number of files to download
        n_en = len(db_entries_list)
        if (args.n > 0):
            n_en = min(n_en, args.n)

        n_downloaded = 0
        for i in range(n_en):
            entry_id = db_entries_list[i]['log_id']
            if args.overwrite or entry_id not in logids:
                file_path = args.download_folder + entry_id + ".ulg"

                r = requests.get(url=args.download_api + "?log=" + entry_id, stream=True)
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                n_downloaded = n_downloaded+1

        print(str(n_downloaded) + ' logs downloaded to ' + args.download_folder)

if __name__ == '__main__':
    main()