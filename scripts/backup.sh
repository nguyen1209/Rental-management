#!/bin/sh
set -eu

backup_root="${BACKUP_DIR:-/var/backups/rental-management}"
retention_days="${BACKUP_RETENTION_DAYS:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$backup_root/$stamp"

mkdir -p "$destination"
docker compose exec -T postgres pg_dump -U "${DB_USER:-rental}" -d "${DB_NAME:-rental}" -Fc > "$destination/database.dump"
tar -C "${UPLOAD_SOURCE:-./uploads}" -czf "$destination/uploads.tar.gz" .
printf '%s\n' "$stamp" > "$destination/created_at.txt"
find "$backup_root" -mindepth 1 -maxdepth 1 -type d -mtime "+$retention_days" -exec rm -rf -- {} +
echo "Backup completed: $destination"
