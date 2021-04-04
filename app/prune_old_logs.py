#! /usr/bin/env python3

# Script to delete old log files & DB entries matching a certain criteria

import sqlite3
import sys
import os
import argparse
import datetime

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.config import get_db_filename, get_overview_img_filepath
from plot_app.helper import get_log_filename


parser = argparse.ArgumentParser(description='Remove old log files & DB entries')

parser.add_argument('--max-age', action='store', type=int, default=30,
        help='maximum age in days (delete logs older than this, default=30)')
parser.add_argument('--source', action='store', default='CI',
        help='Source DB entry tag to match (empty=all, default=CI)')
parser.add_argument('--interactive', '-i', action='store_true', default=False,
        help='Interative mode: ask whether to delete the entries')

args = parser.parse_args()


max_age = args.max_age
source = args.source
interactive = args.interactive

con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
with con:
    cur = con.cursor()
    log_ids_to_remove = []

    if len(source) == 0:
        cur.execute('select Id, Date, Description from Logs')
    else:
        cur.execute('select Id, Date, Description from Logs where Source = ?', [source])

    db_tuples = cur.fetchall()
    print('will delete the following:')
    for db_tuple in db_tuples:
        log_id = db_tuple[0]
        date = db_tuple[1]
        description = db_tuple[2]

        # check date
        elapsed_days = (datetime.datetime.now()-date).days
        if elapsed_days > max_age:
            print('{} {} {}'.format(log_id, date.strftime('%Y_%m_%d-%H_%M'),
                description))
            log_ids_to_remove.append(log_id)


    if len(log_ids_to_remove) == 0:
        print('no maches. exiting')
        exit(0)

    cur.execute('select count(*) from Logs')
    num_total = cur.fetchone()
    if num_total is not None:
        print("Will delete {:} logs out of {:}".format(len(log_ids_to_remove), num_total[0]))

    if interactive:
        confirm = input('Press "y" and ENTER to confirm and delete: ')
        if confirm != 'y':
            print('Not deleting anything')
            exit(0)

    for log_id in log_ids_to_remove:
        print('Removing '+log_id)
        # db entry
        cur.execute("DELETE FROM LogsGenerated WHERE Id = ?", (log_id,))
        cur.execute("DELETE FROM Logs WHERE Id = ?", (log_id,))
        num_deleted = cur.rowcount
        if num_deleted != 1:
            print('Error: not found ({})'.format(num_deleted))
        con.commit()

        # and the log file
        ulog_file_name = get_log_filename(log_id)
        os.unlink(ulog_file_name)
        #and preview image if exist
        preview_image_filename=os.path.join(get_overview_img_filepath(), log_id+'.png')
        if os.path.exists(preview_image_filename):
            os.unlink(preview_image_filename)

con.close()

