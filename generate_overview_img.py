#! /usr/bin/env python3

import os
import sys

import sqlite3

# this is needed for the following imports
sys.path.append(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plot_app'))
from plot_app.overview_generator import generate_overview_img_from_id
from plot_app.config import get_db_filename

# get the logs (but only the public ones)
con = sqlite3.connect(get_db_filename(), detect_types=sqlite3.PARSE_DECLTYPES)
cur = con.cursor()
cur.execute('SELECT Id FROM Logs WHERE Public = 1 ORDER BY Date DESC')
db_tuples = cur.fetchall()

for db_row in db_tuples:    
    log_id=db_row[0]
    generate_overview_img_from_id(log_id)

cur.close()
con.close()

