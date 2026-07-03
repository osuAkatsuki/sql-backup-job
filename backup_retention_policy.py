#!/usr/bin/env python3
"""
A script to delete old backups from wasabi S3 based on a retention policy.

Policy definition:
- Keep all backups that are less than 50 days old
- Keep one backup per half-month from 50 to 180 days old
- Keep one backup per month from 180 to 365 days old
- Keep one backup per quarter after 365 days
- Delete all other backups
"""
from __future__ import annotations

import json
import os.path
import urllib.request
from datetime import datetime
from datetime import timedelta
from datetime import timezone

import boto3
import dotenv

dotenv.load_dotenv()

DAILY_RETENTION_DAYS = 50
SEMI_MONTHLY_RETENTION_DAYS = 180
MONTHLY_RETENTION_DAYS = 365
BYTES_PER_GIB = 1024**3


def parse_backup_time(backup_filepath: str) -> datetime:
    directory = backup_filepath.rstrip("/")
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

    return backup_time.replace(tzinfo=tzinfo)


def get_retention_bucket(
    backup_time: datetime,
    current_time: datetime,
) -> tuple[str, int, int, int] | None:
    age_days = (current_time - backup_time.astimezone(current_time.tzinfo)).days

    if age_days < DAILY_RETENTION_DAYS:
        return None

    if age_days < SEMI_MONTHLY_RETENTION_DAYS:
        half_month = 1 if backup_time.day <= 15 else 2
        return ("semi-month", backup_time.year, backup_time.month, half_month)

    if age_days < MONTHLY_RETENTION_DAYS:
        return ("month", backup_time.year, backup_time.month, 0)

    quarter = (backup_time.month - 1) // 3 + 1
    return ("quarter", backup_time.year, quarter, 0)


def select_backups_to_keep(
    directories: list[str],
    current_time: datetime | None = None,
) -> set[str]:
    if current_time is None:
        current_time = datetime.now(tz=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    kept = set[str]()
    bucketed_backups = dict[tuple[str, int, int, int], tuple[datetime, str]]()
    for directory in directories:
        backup_time = parse_backup_time(directory)
        bucket = get_retention_bucket(backup_time, current_time)
        if bucket is None:
            kept.add(directory)
            continue

        existing = bucketed_backups.get(bucket)
        if existing is None or backup_time < existing[0]:
            bucketed_backups[bucket] = (backup_time, directory)

    kept.update(directory for _, directory in bucketed_backups.values())
    return kept


def list_backup_directories(s3) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    directories = []
    for page in paginator.paginate(
        Bucket=os.environ["S3_BUCKET_NAME"],
        Prefix="db-backups/",
        Delimiter="/",
    ):
        directories.extend(
            obj["Prefix"] for obj in page.get("CommonPrefixes", []) if "Prefix" in obj
        )

    return directories


def list_backup_objects(s3, directory: str) -> list[dict]:
    paginator = s3.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(
        Bucket=os.environ["S3_BUCKET_NAME"],
        Prefix=directory,
    ):
        objects.extend(
            obj for obj in page.get("Contents", []) if "Key" in obj and "Size" in obj
        )

    return objects


def delete_objects(s3, objects: list[dict]) -> None:
    for index in range(0, len(objects), 1000):
        chunk = objects[index : index + 1000]
        s3.delete_objects(
            Delete={"Objects": [{"Key": obj["Key"]} for obj in chunk]},
            Bucket=os.environ["S3_BUCKET_NAME"],
        )


def format_gib(byte_count: float) -> str:
    return f"{byte_count / BYTES_PER_GIB:.2f} GB"


def send_discord_notification(content: str) -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    payload = json.dumps({"username": "Akatsuki", "content": content}).encode()
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except (OSError, TimeoutError, ValueError) as exc:
        print(f"Failed to send Discord notification: {exc}")


def main() -> int:
    s3 = boto3.client(
        service_name="s3",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        region_name=os.environ["AWS_DEFAULT_REGION"],
    )

    directories = list_backup_directories(s3)

    # Figure out which backups to keep and delete
    kept = select_backups_to_keep(directories)
    deleted = set(directories) - kept

    # Delete the backups that should be deleted
    total_bytes_deleted = 0.0
    for directory in sorted(deleted):
        bucket_bytes_deleted = 0.0
        objects = list_backup_objects(s3, directory)
        bucket_bytes_deleted += sum(obj["Size"] for obj in objects)
        delete_objects(s3, objects)

        print(
            f"Deleted {directory} ({len(objects)} objects, {format_gib(bucket_bytes_deleted)})",
        )
        total_bytes_deleted += bucket_bytes_deleted

    # Display stats
    print(f"Kept {len(kept)} backups")
    print(f"Deleted {len(deleted)} backups ({format_gib(total_bytes_deleted)})")
    print(f"Total backups: {len(directories)}")

    send_discord_notification(
        "SQL backup retention completed - "
        f"deleted {len(deleted)} backups ({format_gib(total_bytes_deleted)} reclaimed), "
        f"kept {len(kept)} of {len(directories)} backups.",
    )
    return 0


if __name__ == "__main__":
    exit(main())
