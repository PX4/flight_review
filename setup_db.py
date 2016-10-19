#!/usr/bin/python

import sqlite3 as lite
import sys

from plot_app.config import get_db_filename

print('creating DB at '+get_db_filename())
con = lite.connect(get_db_filename())
with con:
    cur = con.cursor()
    cur.execute("CREATE TABLE Logs(Id TEXT, Title TEXT, Description TEXT, "
            "OriginalFilename TEXT, Date TIMESTAMP, AllowForAnalysis INTEGER, "
            "Obfuscated INTEGER, Source TEXT)")
con.close()

