#!/usr/bin/env bash
set -euo pipefail

# Dump settings
MAX_FILE_SIZE=5368709120 # s3's max file size is 5gb
EXPORT_DIR="export"

echo "Validating environment requirements..."
if [[ -f ".env" ]]; then
    source .env
else
    echo "No .env file found. Exiting."
    exit 1
fi

command -v mysql >/dev/null 2>&1 || { echo >&2 "mysql client is required but it's not installed. Aborting."; exit 1; }
command -v mysqldump >/dev/null 2>&1 || { echo >&2 "mysqldump is required but it's not installed. Aborting."; exit 1; }

if [[ -d $EXPORT_DIR ]]; then
    rm -rf $EXPORT_DIR
fi

mkdir $EXPORT_DIR

echo "Dumping all databases..."

MASTER_ONLY_PARAMS=""
if [[ -n "$IS_MASTER_DB" ]]; then
    MASTER_ONLY_PARAMS="--source-data"
fi

mysqldump --all-databases --single-transaction $MASTER_ONLY_PARAMS \
          -h$DB_HOST -P$DB_PORT -u$DB_USER --password=$DB_PASS \
          > "$EXPORT_DIR/backup.sql"

echo "Compressing with gzip..."
gzip "$EXPORT_DIR/backup.sql"

echo "Dividing into parts..."
split -b $MAX_FILE_SIZE "$EXPORT_DIR/backup.sql.gz" "$EXPORT_DIR/backup.sql.gz.part-"
rm "$EXPORT_DIR/backup.sql.gz"

echo "Syncing to S3..."
backup_name=$(date +'%d-%m-%YT%H:%M')
time aws s3 sync \
    --endpoint-url=$S3_ENDPOINT_URL \
    $EXPORT_DIR \
    s3://$S3_BUCKET_NAME/db-backups/$backup_name

if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    echo "Sending notification to Discord..."
    curl \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"Akatsuki\", \"content\": \"Successfully backed up MySQL production database - $(du -sh $EXPORT_DIR | cut -f1)\"}" \
        $DISCORD_WEBHOOK_URL
fi

echo "Cleaning up..."
rm -rf $EXPORT_DIR

echo "Done!"
