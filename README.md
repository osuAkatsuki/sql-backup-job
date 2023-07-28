# sql-backup-job

a mysql backup bash script for syncing to s3

handles 5gb s3 upload limit by dividing the export into 5gb files and syncing them to a directory in s3
