#!/usr/bin/env python3

"""
A script to delete old backups from wasabi S3 based on a retention policy.

Policy definition:
- Keep all backups that are less than 50 days old
- Keep all backups that are either on the midpoint of the month or the first day of the month
- Delete all other backups
"""

import os
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import boto3
import dotenv

dotenv.load_dotenv()


def should_keep_backup(backup_filepath: str) -> bool:
    try:
        # New: 'db-backups/2024-02-01T04:08Z/'
        backup_date = datetime.strptime(
            backup_filepath,
            "db-backups/%Y-%m-%dT%H:%MZ/",
        )
        tzinfo = timezone.utc
    except ValueError:
        # Old: 'db-backups/01-01-2024T04:08/'
        backup_date = datetime.strptime(
            backup_filepath,
            "db-backups/%d-%m-%YT%H:%M/",
        )
        # Backups were previously named in EST
        tzinfo = timezone(timedelta(hours=-4))

    backup_date = backup_date.replace(tzinfo=tzinfo)
    current_date = datetime.now(tz=tzinfo)

    if (current_date - backup_date).days < 50:
        return True

    if backup_date.day == 15 or backup_date.day == 1:
        return True

    return False


def main() -> int:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        region_name=os.environ["AWS_DEFAULT_REGION"],
    )

    response = s3.list_objects_v2(
        Bucket=os.environ["S3_BUCKET_NAME"],
        Prefix="db-backups/",
        Delimiter="/",
    )

    # Figure out which backups to keep and delete
    kept = set()
    deleted = set()
    for obj in response["CommonPrefixes"]:
        key = obj["Prefix"]
        if should_keep_backup(key):
            kept.add(key)
        else:
            deleted.add(key)

    # Delete the backups that should be deleted
    for key in deleted:
        print(f"Deleting {key}")
        s3.delete_object(Bucket=os.environ["S3_BUCKET_NAME"], Key=key)

    # Display stats
    print(f"Kept {len(kept)} backups")
    print(f"Deleted {len(deleted)} backups")
    print(f"Total backups: {len(response['CommonPrefixes'])}")
    return 0


if __name__ == "__main__":
    exit(main())
