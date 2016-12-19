#!/usr/bin/python

# Script to backup the SQLite DB

from __future__ import print_function
import sys
import os
import datetime

from plot_app.config import get_db_filename

db_filename = get_db_filename()
backup_file = "backups/backup_db_"+ \
    datetime.datetime.now().strftime('%Y_%m_%d-%H_%M')

if not os.path.exists('backups'):
    os.mkdir('backups')

os.system('sqlite3 '+db_filename+' ".backup '+backup_file+'.sqlite"')
os.system('sqlite3 '+db_filename+' "SELECT * from Logs" >'+backup_file+'.sql')

num_lines = sum(1 for line in open(backup_file+'.sql'))
print('Backed up {} records to {}'.format(num_lines, backup_file+'.sqlite'))

