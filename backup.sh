#!/usr/bin/env bash
set -euo pipefail

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

command -v age >/dev/null 2>&1 || { echo >&2 "age is required to encrypt backups."; exit 1; }
: "${BACKUP_AGE_RECIPIENT:?Set BACKUP_AGE_RECIPIENT to the backup public key}"
# Check the recipient before touching the database.
age -r "$BACKUP_AGE_RECIPIENT" </dev/null >/dev/null

umask 077
EXPORT_DIR=$(mktemp -d)
trap 'rm -rf -- "$EXPORT_DIR"' EXIT

echo "Dumping all tables in $DB_NAME database.."

dump_options=(--single-transaction --no-tablespaces)
if [[ "$INCLUDE_MASTER_REPLICATION_DATA" = "true" ]]; then
    dump_options+=(--source-data)
fi

tables=$(mysql -NBA -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" -D "$DB_NAME" -e 'show tables')
while IFS= read -r table_name; do
    [[ -n "$table_name" ]] || continue
    echo "Dumping table: $DB_NAME.$table_name"
    mysqldump "${dump_options[@]}" \
        -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" "$table_name" |
        gzip | age -r "$BACKUP_AGE_RECIPIENT" -o "$EXPORT_DIR/$DB_NAME.$table_name.sql.gz.age"
done <<< "$tables"

echo "Syncing to S3..."
backup_name=$(date -u +'%Y-%m-%dT%H:%MZ')
time aws s3 sync \
    --endpoint-url="$S3_ENDPOINT_URL" \
    --no-progress \
    "$EXPORT_DIR" \
    "s3://$S3_BUCKET_NAME/db-backups/$backup_name"

if [[ -n "${DISCORD_WEBHOOK_URL:-}" ]]; then
    echo "Sending notification to Discord..."
    curl \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"Akatsuki\", \"content\": \"Successfully backed up MySQL production database - $(du -sh "$EXPORT_DIR" | cut -f1)\"}" \
        $DISCORD_WEBHOOK_URL
fi

echo "Done!"
