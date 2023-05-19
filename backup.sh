#!/usr/bin/env bash
set -euo pipefail

if [[ -f ".env" ]]; then
    source .env
else
    echo "No .env file found. Exiting."
    exit 1
fi

# Dump settings
PAGE_SIZE=1000000 # 1 million
EXPORT_DIR="export"

command -v mysql >/dev/null 2>&1 || { echo >&2 "mysql client is required but it's not installed.  Aborting."; exit 1; }
command -v mysqldump >/dev/null 2>&1 || { echo >&2 "mysqldump is required but it's not installed.  Aborting."; exit 1; }

if [[ ! -d $EXPORT_DIR ]]; then
    mkdir $EXPORT_DIR
fi

tables=$(
    echo "show tables" |
    mysql -u$DB_USER -h$DB_HOST -P$DB_PORT --password=$DB_PASS $DB_NAME 2>/dev/null |
    grep -v "Tables_in_"
)

for table in $tables; do
    echo "Dumping table: $table"

    row_count=$(mysql -u$DB_USER --password=$DB_PASS -h$DB_HOST -P$DB_PORT --raw --batch -e "SELECT COUNT(*) FROM $DB_NAME.$table" -s 2>/dev/null)

    page_count="$((1 + (row_count / PAGE_SIZE)))"
    echo "Rows: $row_count ($page_count page(s))"

    page=1

    while [ $page -le $page_count ]; do

        export_file_name="$EXPORT_DIR/${table}_$page.sql"
        echo "Dumping page #$page to $export_file_name"

        offset=$(((page - 1) * PAGE_SIZE))

        if [ $page == 1 ]; then

            # include additional info on our first page
            mysqldump \
                -h$DB_HOST -P$DB_PORT \
                -u$DB_USER --password=$DB_PASS \
                --add-drop-table \
                --add-locks \
                --skip-disable-keys \
                --create-options \
                --extended-insert \
                --lock-tables \
                --set-charset \
                --no-tablespaces \
                --where "1 LIMIT $PAGE_SIZE OFFSET $offset" \
                $DB_NAME $table > $export_file_name \
                2>/dev/null
        else
            mysqldump \
                -h$DB_HOST -P$DB_PORT \
                -u$DB_USER --password=$DB_PASS \
                --skip-add-drop-table \
                --skip-add-locks \
                --skip-disable-keys \
                --skip-set-charset \
                --no-create-info \
                --single-transaction \
                --no-tablespaces \
                --where="1 LIMIT $PAGE_SIZE OFFSET $offset" \
                $DB_NAME $table > $export_file_name \
                2>/dev/null
        fi

        page=$((page + 1))
        echo # \n
    done
done

echo "Done!"
