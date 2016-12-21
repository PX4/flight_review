#!/usr/bin/python

# Script to create or upgrade the SQLite DB

import sqlite3 as lite
import sys
import os

from plot_app.config import get_db_filename, get_log_filepath, \
    get_cache_filepath, get_kml_filepath

log_dir = get_log_filepath()
if not os.path.exists(log_dir):
    print('creating log directory '+log_dir)
    os.makedirs(log_dir)

cur_dir = get_cache_filepath()
if not os.path.exists(cur_dir):
    print('creating cache directory '+cur_dir)
    os.makedirs(cur_dir)

cur_dir = get_kml_filepath()
if not os.path.exists(cur_dir):
    print('creating kml directory '+cur_dir)
    os.makedirs(cur_dir)


print('creating DB at '+get_db_filename())
con = lite.connect(get_db_filename())
with con:
    cur = con.cursor()

    # Logs table (contains information not found in the log file)
    cur.execute("PRAGMA table_info('Logs')")
    columns = cur.fetchall()

    if len(columns) == 0:
        cur.execute("CREATE TABLE Logs("
                "Id TEXT, " # log id (part of the file name)
                "Title TEXT, "
                "Description TEXT, "
                "OriginalFilename TEXT, "
                "Date TIMESTAMP, " # date & time when uploaded
                "AllowForAnalysis INTEGER, " # if 1 allow for statistical analysis
                "Obfuscated INTEGER, "
                "Source TEXT, " # where it comes from: 'webui', 'CI', 'QGroundControl'
                "Email TEXT, " # email (may be empty)
                "WindSpeed INT, " # Wind speed in beaufort scale
                "Rating TEXT, " # how the flight was rated
                "Feedback TEXT, " # additional feedback
                "Type TEXT, " # upload type: 'personal' (or '') or 'flightreport'
                "VideoUrl TEXT, "
                "Public INT, " # if 1 this log can be publicly listed
                "Token TEXT, " # Security token (currently used to delete the entry)
                "CONSTRAINT Id_PK PRIMARY KEY (Id))")
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
        if not 'Public' in column_names:
            print('Adding column Public')
            cur.execute("ALTER TABLE Logs ADD COLUMN Public INT DEFAULT 0")
        if not 'Token' in column_names:
            print('Adding column Token')
            cur.execute("ALTER TABLE Logs ADD COLUMN Token TEXT DEFAULT ''")


    # LogsGenerated table (information from the log file, for faster access)
    cur.execute("PRAGMA table_info('LogsGenerated')")
    columns = cur.fetchall()

    if len(columns) == 0:
        cur.execute("CREATE TABLE LogsGenerated("
                "Id TEXT, " # log id
                "Duration INT, " # logging duration in [s]
                "MavType TEXT, " # vehicle type
                "Estimator TEXT, "
                "AutostartId INT, " # airframe config
                "Hardware TEXT, " # board
                "Software TEXT, " # software (git tag)
                "NumLoggedErrors INT, " # number of logged error messages (or more severe)
                "NumLoggedWarnings INT, "
                "FlightModes TEXT, " # all flight modes as comma-separated int's
                "SoftwareVersion TEXT, " # release version
                "CONSTRAINT Id_PK PRIMARY KEY (Id))")

    else:
        # try to upgrade
        column_names = [ x[1] for x in columns]

        if not 'SoftwareVersion' in column_names:
            print('Adding column SoftwareVersion')
            cur.execute("ALTER TABLE LogsGenerated ADD COLUMN SoftwareVersion TEXT DEFAULT ''")

con.close()

