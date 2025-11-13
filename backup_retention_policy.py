#!/usr/bin/env python3
"""
A script to delete old backups from wasabi S3 based on a retention policy.

Policy definition:
- Keep all backups that are less than 50 days old
- Keep all backups that are either on the midpoint of the month or the first day of the month
- Delete all other backups
"""
from __future__ import annotations

import os.path
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import boto3
import dotenv

dotenv.load_dotenv()


def should_keep_backup(backup_filepath: str) -> bool:
    directory, _ = os.path.split(backup_filepath)
    try:
        # New: 'db-backups/2024-02-01T04:08Z'
        backup_time = datetime.strptime(
            directory,
            "db-backups/%Y-%m-%dT%H:%MZ",
        )
        tzinfo = timezone.utc
    except ValueError:
        # Old: 'db-backups/01-01-2024T04:08'
        backup_time = datetime.strptime(
            directory,
            "db-backups/%d-%m-%YT%H:%M",
        )
        # Backups were previously named in EST
        tzinfo = timezone(timedelta(hours=-4))

    backup_time = backup_time.replace(tzinfo=tzinfo)
    current_time = datetime.now(tz=tzinfo)

    if (current_time - backup_time).days < 50:
        return True

    if backup_time.day == 15 or backup_time.day == 1:
        return True

    return False


def main() -> int:
    s3 = boto3.client(
        service_name="s3",
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
    directories = [
        obj["Prefix"] for obj in response.get("CommonPrefixes", []) if "Prefix" in obj
    ]

    # Figure out which backups to keep and delete
    kept = set[str]()
    deleted = set[str]()
    for directory in directories:
        if should_keep_backup(directory):
            kept.add(directory)
        else:
            deleted.add(directory)

    # Delete the backups that should be deleted
    total_bytes_deleted = 0.0
    for directory in deleted:
        bucket_bytes_deleted = 0.0
        response = s3.list_objects_v2(
            Bucket=os.environ["S3_BUCKET_NAME"],
            Prefix=directory,
        )
        objects = [
            obj
            for obj in response.get("Contents", [])
            if "Key" in obj and "Size" in obj
        ]
        bucket_bytes_deleted += sum(obj["Size"] for obj in objects)
        s3.delete_objects(
            Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
            Bucket=os.environ["S3_BUCKET_NAME"],
        )

        print(
            f"Deleted {directory} ({len(objects)} objects, {bucket_bytes_deleted / 1024 ** 3:.2f} GB)",
        )
        total_bytes_deleted += bucket_bytes_deleted

    # Display stats
    print(f"Kept {len(kept)} backups")
    print(f"Deleted {len(deleted)} backups ({total_bytes_deleted / 1024 ** 3:.2f} GB)")
    print(f"Total backups: {len(directories)}")
    return 0


if __name__ == "__main__":
    exit(main())
