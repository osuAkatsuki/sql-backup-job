#!/usr/bin/env bash
set -euo pipefail

if [[ -f ".env" ]]; then
    source .env
else
    echo "No .env file found. Exiting."
    exit 1
fi

# Dump settings
MAX_FILE_SIZE=1000000000 # 1gb
EXPORT_DIR="export"

command -v mysql >/dev/null 2>&1 || { echo >&2 "mysql client is required but it's not installed. Aborting."; exit 1; }
command -v mysqldump >/dev/null 2>&1 || { echo >&2 "mysqldump is required but it's not installed. Aborting."; exit 1; }

if [[ ! -d $EXPORT_DIR ]]; then
    mkdir $EXPORT_DIR
fi

echo "Dumping database..."
mysqldump -h$DB_HOST -P$DB_PORT -u$DB_USER --password=$DB_PASS $DB_NAME > "$EXPORT_DIR/backup.sql" 2>/dev/null

echo "Dividing into parts..."
split -b $MAX_FILE_SIZE "$EXPORT_DIR/backup.sql" "$EXPORT_DIR/backup.sql.part-"

echo "Compressing..."
rm "$EXPORT_DIR/backup.sql"

echo "Syncing to S3..."
backup_name=$(date +'%d-%m-%YT%H:%M')
time aws s3 sync \
    --endpoint-url=$S3_ENDPOINT_URL \
    $EXPORT_DIR \
    s3://$S3_BUCKET_NAME/db-backups/$backup_name

echo "Cleaning up..."
rm -rf $EXPORT_DIR

echo "Done!"
