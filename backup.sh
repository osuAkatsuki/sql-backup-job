#!/usr/bin/env bash
set -euo pipefail

if [[ -f ".env" ]]; then
    source .env
fi

DB_USER=cmyui
DB_PASS=lol123
DB_NAME=akatsuki
DB_HOST=localhost
DB_PORT=3306

PAGE_SIZE=1000000 # 1 million

dump_database() {
    tables=$(
        echo "show tables"
            | mysql -u$DB_USER -h$DB_HOST -P$DB_PORT -p$DB_PASS $DB_NAME
            | grep -v "Tables_in_" \
              2>&1 | grep -v "Warning: Using a password"
    )

    for table in $tables; do
        echo "Dumping table: $table"

        row_count=$(mysql -u$DB_USER -h$DB_HOST -P$DB_PORT -p$DB_PASS --raw --batch -e "SELECT COUNT(*) FROM $DB_NAME.$table" -s)
        page_count=$((1 + (row_count / PAGE_SIZE)))
        echo "Rows: $row_count ($page_count pages)"

        page=1

        while [ $page -le $page_count ]; do

            export_file_name="export/${table}_$page.sql"
            echo "Dumping page #$page to $export_file_name"

            offset=$(((page - 1) * PAGE_SIZE))

            if [ $page == 1 ]; then

                # include additional info on our first page
                mysqldump \
                    -h$DB_HOST -P$DB_PORT \
                    -u$DB_USER -p$DB_PASS \
                    --add-drop-table \
                    --add-locks \
                    --skip-disable-keys \
                    --create-options \
                    --extended-insert \
                    --lock-tables \
                    --set-charset \
                    --no-tablespaces \
                    --where "1 LIMIT $PAGE_SIZE OFFSET $offset" \
                    $DB_NAME $table \
                    2>&1 | grep -v "Warning: Using a password" \
                    > $export_file_name
            else
                mysqldump \
                    -h$DB_HOST -P$DB_PORT \
                    -u$DB_USER -p$DB_PASS \
                    --skip-add-drop-table \
                    --skip-add-locks \
                    --skip-comments \
                    --skip-disable-keys \
                    --skip-set-charset \
                    --skip-triggers \
                    --no-create-info \
                    --single-transaction \
                    --no-tablespaces \E
                    --where="1 LIMIT $PAGE_SIZE OFFSET $offset" \
                    $DB_NAME $table \
                    2>&1 | grep -v "Warning: Using a password" \
                    > $export_file_name
            fi

            page=$((page + 1))
        done
    done

    echo "Done!"
}

dump_database
