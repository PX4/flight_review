#!/usr/bin/python

# Script to create or upgrade the SQLite DB

import sqlite3 as lite
import sys
import os

from plot_app.config import get_db_filename, get_log_filepath

log_dir = get_log_filepath()
if not os.path.exists(log_dir):
    print('creating log directory '+log_dir)
    os.makedirs(log_dir)

print('creating DB at '+get_db_filename())
con = lite.connect(get_db_filename())
with con:
    cur = con.cursor()
    cur.execute("PRAGMA table_info('Logs')")
    columns = cur.fetchall()

    if len(columns) == 0:
        cur.execute("CREATE TABLE Logs(Id TEXT, Title TEXT, Description TEXT, "
                "OriginalFilename TEXT, Date TIMESTAMP, AllowForAnalysis INTEGER, "
                "Obfuscated INTEGER, Source TEXT, Email TEXT, WindSpeed INT, "
                "Rating TEXT, Feedback TEXT, Type TEXT, VideoUrl TEXT)")
    else:
        # try to upgrade
        column_names = [ x[1] for x in columns]
        if not 'Email' in column_names:
            print('Adding column Email')
            cur.execute("ALTER TABLE Logs ADD COLUMN Email TEXT DEFAULT ''")
        if not 'WindSpeed' in column_names:
            print('Adding column WindSpeed')
            cur.execute("ALTER TABLE Logs ADD COLUMN WindSpeed INT DEFAULT -1")
        if not 'Rating' in column_names:
            print('Adding column Rating')
            cur.execute("ALTER TABLE Logs ADD COLUMN Rating TEXT DEFAULT ''")
        if not 'Feedback' in column_names:
            print('Adding column Feedback')
            cur.execute("ALTER TABLE Logs ADD COLUMN Feedback TEXT DEFAULT ''")
        if not 'Type' in column_names:
            print('Adding column Type')
            cur.execute("ALTER TABLE Logs ADD COLUMN Type TEXT DEFAULT ''")
        if not 'VideoUrl' in column_names:
            print('Adding column VideoUrl')
            cur.execute("ALTER TABLE Logs ADD COLUMN VideoUrl TEXT DEFAULT ''")

con.close()

