#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || [ ! -d "$1" ]; then
  echo "Usage: $0 /path/to/backup-directory" >&2
  exit 2
fi

backup_dir="$1"
test -f "$backup_dir/database.dump"
test -f "$backup_dir/uploads.tar.gz"
docker compose exec -T postgres pg_restore -U "${DB_USER:-rental}" -d "${DB_NAME:-rental}" --clean --if-exists < "$backup_dir/database.dump"
mkdir -p "${UPLOAD_SOURCE:-./uploads}"
tar -C "${UPLOAD_SOURCE:-./uploads}" -xzf "$backup_dir/uploads.tar.gz"
echo "Restore completed from: $backup_dir"
