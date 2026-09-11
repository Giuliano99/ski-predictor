#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
environment_file="$runtime_root/config/runtime.env"
backup_root="$runtime_root/backups"
retention_days="${SKI_BACKUP_RETENTION_DAYS:-14}"

if [[ ! -f "$environment_file" ]]; then
  echo "Laufzeitkonfiguration fehlt: $environment_file" >&2
  exit 1
fi

if [[ "$backup_root" != "$runtime_root/backups" || "$runtime_root" == "/" ]]; then
  echo "Unsicherer Backup-Pfad: $backup_root" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a

compose=(docker compose --env-file "$environment_file" -f "$repo_dir/compose.pi.yaml")
backup_id="$(date -u +%Y%m%dT%H%M%SZ)"
partial_directory="$backup_root/.partial-$backup_id"
final_directory="$backup_root/$backup_id"

umask 077
mkdir -p "$partial_directory"

cleanup_partial() {
  if [[ -d "$partial_directory" ]]; then
    rm -rf -- "$partial_directory"
  fi
}
trap cleanup_partial EXIT

"${compose[@]}" exec -T database \
  pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format custom \
  >"$partial_directory/database.dump"

tar -czf "$partial_directory/state.tar.gz" -C "$runtime_root/state" .
tar -czf "$partial_directory/documents.tar.gz" -C "$runtime_root/documents" .

(
  cd "$partial_directory"
  sha256sum database.dump state.tar.gz documents.tar.gz >SHA256SUMS
)

mv "$partial_directory" "$final_directory"
trap - EXIT
ln -sfn "$backup_id" "$backup_root/latest"

find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' \
  -mtime "+$retention_days" -exec rm -rf -- {} +

echo "Backup erstellt: $final_directory"
