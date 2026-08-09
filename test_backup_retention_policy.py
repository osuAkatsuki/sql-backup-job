from __future__ import annotations

import json
import os
import unittest
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest import mock

import backup_retention_policy


class BackupRetentionPolicyTest(unittest.TestCase):
    def test_retention_bucket_boundaries(self) -> None:
        current_time = datetime(2026, 8, 3, 4, 18, tzinfo=timezone.utc)

        self.assertIsNone(
            backup_retention_policy.get_retention_bucket(
                current_time - timedelta(days=9),
                current_time,
            ),
        )

        ten_days_old = current_time - timedelta(days=10)
        iso_year, iso_week, _ = ten_days_old.isocalendar()
        self.assertEqual(
            backup_retention_policy.get_retention_bucket(
                ten_days_old,
                current_time,
            ),
            ("week", iso_year, iso_week, 0),
        )

        fifty_nine_days_old = current_time - timedelta(days=59)
        iso_year, iso_week, _ = fifty_nine_days_old.isocalendar()
        self.assertEqual(
            backup_retention_policy.get_retention_bucket(
                fifty_nine_days_old,
                current_time,
            ),
            ("week", iso_year, iso_week, 0),
        )

        sixty_days_old = current_time - timedelta(days=60)
        self.assertEqual(
            backup_retention_policy.get_retention_bucket(
                sixty_days_old,
                current_time,
            ),
            ("month", sixty_days_old.year, sixty_days_old.month, 0),
        )

        three_hundred_sixty_four_days_old = current_time - timedelta(days=364)
        self.assertEqual(
            backup_retention_policy.get_retention_bucket(
                three_hundred_sixty_four_days_old,
                current_time,
            ),
            (
                "month",
                three_hundred_sixty_four_days_old.year,
                three_hundred_sixty_four_days_old.month,
                0,
            ),
        )

        year_old = current_time - timedelta(days=365)
        self.assertEqual(
            backup_retention_policy.get_retention_bucket(
                year_old,
                current_time,
            ),
            ("quarter", year_old.year, (year_old.month - 1) // 3 + 1, 0),
        )

    def test_selects_tiered_backup_buckets(self) -> None:
        current_time = datetime(2026, 8, 3, 6, tzinfo=timezone.utc)
        directories = [
            "db-backups/2026-07-30T04:18Z/",
            "db-backups/2026-07-20T04:18Z/",
            "db-backups/2026-07-21T04:18Z/",
            "db-backups/2026-07-13T04:18Z/",
            "db-backups/2026-07-14T04:18Z/",
            "db-backups/2026-06-10T04:18Z/",
            "db-backups/2026-06-11T04:18Z/",
            "db-backups/2026-05-01T04:18Z/",
            "db-backups/2026-05-15T04:18Z/",
            "db-backups/2026-01-01T04:18Z/",
            "db-backups/2026-01-15T04:18Z/",
            "db-backups/2025-03-01T04:18Z/",
            "db-backups/2025-04-01T04:18Z/",
            "db-backups/2025-06-01T04:18Z/",
        ]

        kept = backup_retention_policy.select_backups_to_keep(
            directories,
            current_time=current_time,
        )

        self.assertEqual(
            kept,
            {
                "db-backups/2026-07-30T04:18Z/",
                "db-backups/2026-07-20T04:18Z/",
                "db-backups/2026-07-13T04:18Z/",
                "db-backups/2026-06-10T04:18Z/",
                "db-backups/2026-05-01T04:18Z/",
                "db-backups/2026-01-01T04:18Z/",
                "db-backups/2025-03-01T04:18Z/",
                "db-backups/2025-04-01T04:18Z/",
            },
        )

    def test_send_discord_notification_uses_backup_webhook(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://discord.example/webhook"},
        ):
            with mock.patch("urllib.request.urlopen") as urlopen:
                backup_retention_policy.send_discord_notification("hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://discord.example/webhook")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(
            request.headers["User-agent"],
            "Akatsuki SQL Backup Retention",
        )
        self.assertEqual(
            json.loads(request.data.decode()),
            {"username": "Akatsuki", "content": "hello"},
        )

    def test_delete_objects_uses_s3_bucket_name(self) -> None:
        s3 = mock.Mock()
        objects = [{"Key": "one"}, {"Key": "two"}]

        with mock.patch.dict(os.environ, {"S3_BUCKET_NAME": "akatsuki.pw"}):
            backup_retention_policy.delete_objects(s3, objects)

        s3.delete_objects.assert_called_once_with(
            Delete={"Objects": [{"Key": "one"}, {"Key": "two"}]},
            Bucket="akatsuki.pw",
        )


if __name__ == "__main__":
    unittest.main()
