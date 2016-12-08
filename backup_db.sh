#! /bin/bash

db_file="data/logs.sqlite"
backup_file="backups/backup_db_`date +%Y-%m-%d`"
[ ! -d backups ] && mkdir backups

cp $db_file ${backup_file}.sqlite
sqlite3 $db_file "select * from Logs" >${backup_file}.sql
echo "Backed up `wc -l ${backup_file}.sql` records from DB"
