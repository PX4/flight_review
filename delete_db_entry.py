#! /usr/bin/env python3

# Script to remove a single DB entry

import sqlite3 as lite
import sys
import os
import argparse

from plot_app.config import get_db_filename


parser = argparse.ArgumentParser(description='Remove a DB entry (but not the log file)')

parser.add_argument('log_id', metavar='log-id', action='store', nargs='+',
        help='log id to remove (eg. 8600ac02-cf06-4650-bdd5-7d27ea081852)')

args = parser.parse_args()

con = lite.connect(get_db_filename())
with con:
    cur = con.cursor()
    for log_id in args.log_id:
        print('Removing '+log_id)
        cur.execute("DELETE FROM LogsGenerated WHERE Id = ?", (log_id,))
        cur.execute("DELETE FROM Logs WHERE Id = ?", (log_id,))
        num_deleted = cur.rowcount
        if num_deleted != 1:
            print('Error: not found ({})'.format(num_deleted))
        con.commit()

con.close()

