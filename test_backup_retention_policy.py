from __future__ import annotations

import json
import os
import unittest
from datetime import datetime
from datetime import timezone
from unittest import mock

import backup_retention_policy


class BackupRetentionPolicyTest(unittest.TestCase):
    def test_selects_tiered_backup_buckets(self) -> None:
        current_time = datetime(2026, 8, 3, tzinfo=timezone.utc)
        directories = [
            "db-backups/2026-06-20T04:18Z/",
            "db-backups/2026-05-10T04:18Z/",
            "db-backups/2026-05-12T04:18Z/",
            "db-backups/2026-05-20T04:18Z/",
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
                "db-backups/2026-06-20T04:18Z/",
                "db-backups/2026-05-10T04:18Z/",
                "db-backups/2026-05-20T04:18Z/",
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
