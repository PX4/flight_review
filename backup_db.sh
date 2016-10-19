#! /bin/bash

db_file="data/logs.sqlite"
backup_file="backups/backup_db_`date +%Y-%m-%d`.sql"
[ ! -d backups ] && mkdir backups

sqlite3 $db_file "select * from Logs" >$backup_file
echo "Backed up `wc -l $backup_file` records from DB"
