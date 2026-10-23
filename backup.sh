#!/usr/bin/env bash
set -euo pipefail

# Dump settings
MAX_FILE_SIZE=5368709120 # s3's max file size is 5gb
EXPORT_DIR="export"

echo "Validating environment requirements..."
if [[ -f ".env" ]]; then
    source .env
    # The aws CLI only reads exported variables; otherwise it falls back to ~/.aws
    export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
           AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
           AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION"
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

echo "Dumping all tables in $DB_NAME database.."

MASTER_ONLY_PARAMS=""
if [[ "$INCLUDE_MASTER_REPLICATION_DATA" = "true" ]]; then
    MASTER_ONLY_PARAMS="--source-data"
fi

tbl_count=0
for table_name in $(mysql -NBA -h $DB_HOST -u $DB_USER -p$DB_PASS -D $DB_NAME -e 'show tables')
do
    echo "Dumping table: $DB_NAME.$table_name"
    mysqldump --single-transaction --no-tablespaces $MASTER_ONLY_PARAMS \
              -h$DB_HOST -u$DB_USER -p$DB_PASS \
              $DB_NAME $table_name | gzip > $EXPORT_DIR/$DB_NAME.$table_name.sql.gz
    tbl_count=$(( tbl_count + 1 ))
done

echo "Dumping MySQL accounts and their privileges.."
# Statements that recreate each account (with its password hash) and its grants. Accounts that
# MySQL or the OS package create on install are skipped. Raw output (-r) keeps each QUOTE()d
# account a valid SQL literal. Failures here are reported but don't stop the table backup.
if ! mysql -NBAr -h $DB_HOST -u $DB_USER -p$DB_PASS -e "
        SELECT CONCAT(QUOTE(user), '@', QUOTE(host)) FROM mysql.user
        WHERE user NOT IN ('root', 'debian-sys-maint', 'mysql.sys', 'mysql.session', 'mysql.infoschema')" |
    while IFS= read -r account; do
        mysql -NBAr -h $DB_HOST -u $DB_USER -p$DB_PASS \
              -e "SET print_identified_with_as_hex = ON; SHOW CREATE USER $account; SHOW GRANTS FOR $account" \
            | sed -e 's/^CREATE USER /CREATE USER IF NOT EXISTS /' -e 's/$/;/' \
            || echo >&2 "Failed to dump account $account"
    done | gzip > $EXPORT_DIR/mysql.accounts.sql.gz
then
    echo >&2 "Failed to dump MySQL accounts"
fi

# echo "Dividing into parts..."
# split -b $MAX_FILE_SIZE "$EXPORT_DIR/backup.sql.gz" "$EXPORT_DIR/backup.sql.gz.part-"
# rm "$EXPORT_DIR/backup.sql.gz"

echo "Syncing to S3..."
backup_name=$(date --universal +'%Y-%m-%dT%H:%MZ')
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
