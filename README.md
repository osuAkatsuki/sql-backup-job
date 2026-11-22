# sql-backup-job

Install `age` on the backup host and set `BACKUP_AGE_RECIPIENT` in `.env` to the
public recipient. Store the corresponding private identity separately from the
backup host and bucket. Each uploaded `.sql.gz.age` object contains one encrypted,
gzip-compressed table dump.

To inspect a downloaded dump during a restore:

```sh
age --decrypt --identity /path/to/restore-identity table.sql.gz.age | gzip -dc
```
