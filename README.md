# sql-backup-job

a mysql backup bash script for syncing to s3

a couple of features:
- s3 has a per-file upload limit of 5gb. we gzip compress and split files into 5gb chunks
- if the job is being run on a master node, we include the binlog offsets
- sends a discord webhook upon completion of a run
