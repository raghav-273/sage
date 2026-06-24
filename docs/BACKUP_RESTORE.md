# SAGE — Backup and Restore

## The one rule that matters

**Always back up and restore PostgreSQL and `media/` together, from the
same point in time.** `Document.file_path` and `DiagramAsset.image_path`
are database rows that point at files on disk. Restore the database
without the matching `media/` snapshot and every document points at a
file that doesn't exist. Restore `media/` without the matching database
and you get orphaned files with no row referencing them. Neither half
is useful without the other from the same moment — this isn't a
theoretical concern, it's the direct consequence of how this project
stores files (paths in Postgres, bytes on disk, deliberately never
binary blobs in the database).

## Backup

```bash
mkdir -p backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 1. Database — custom format (-F c): compressed, supports selective
#    restore via pg_restore, unlike a plain SQL dump.
docker compose exec db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c \
  -f /tmp/sage_db_${TIMESTAMP}.dump
docker compose cp db:/tmp/sage_db_${TIMESTAMP}.dump backups/

# 2. media/ — this is a host bind mount, not a Docker volume, so it's
#    already a real directory on your machine. No docker cp dance needed.
tar -czf backups/sage_media_${TIMESTAMP}.tar.gz media/

echo "Backup pair: sage_db_${TIMESTAMP}.dump + sage_media_${TIMESTAMP}.tar.gz"
```

The shared `${TIMESTAMP}` in both filenames is deliberate — it's the
simplest way to make it visually obvious which two files belong
together, and hard to accidentally mix up later.

## Restore

```bash
# Pick a matching pair from backups/ — DB_DUMP and MEDIA_ARCHIVE must
# share the same timestamp.
DB_DUMP=backups/sage_db_20260624_140000.dump
MEDIA_ARCHIVE=backups/sage_media_20260624_140000.tar.gz

# 1. Database — --clean drops existing objects first; --if-exists
#    suppresses errors on a fresh/empty target database.
docker compose cp "$DB_DUMP" db:/tmp/restore.dump
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --clean --if-exists /tmp/restore.dump

# 2. media/ — restore into the same host directory Django reads from.
rm -rf media
tar -xzf "$MEDIA_ARCHIVE"

# 3. Restart so the app picks up the restored state cleanly.
docker compose restart web celery_worker
```

## Verifying a restore actually worked

A restore that "completes without error" can still leave a mismatch if
the wrong pair of files was used. Spot-check a few documents directly:

```bash
docker compose exec web python manage.py shell -c "
from pathlib import Path
from django.conf import settings
from apps.documents.models import Document

for doc in Document.objects.all()[:5]:
    path = Path(settings.MEDIA_ROOT) / doc.file_path
    print(doc.name, '->', path, 'EXISTS' if path.exists() else 'MISSING')
"
```

Every row should print `EXISTS`. Any `MISSING` result means the database
and `media/` snapshots came from different points in time — re-restore
with a correctly matched pair.

## What this does not cover

This is file-and-database backup, not a disaster-recovery system —
there's no automated schedule, no off-host replication, and no
retention policy. For a single-operator demo deployment, a manual
backup before any risky change (a migration, a bulk re-ingestion) is the
intended usage pattern, not a cron job. Automating this is a reasonable
future addition, not something this milestone implements.