#!/usr/bin/python

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
    cur.execute("CREATE TABLE Logs(Id TEXT, Title TEXT, Description TEXT, "
            "OriginalFilename TEXT, Date TIMESTAMP, AllowForAnalysis INTEGER, "
            "Obfuscated INTEGER, Source TEXT)")
con.close()

