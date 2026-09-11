#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
environment_file="$runtime_root/config/runtime.env"
backup_directory="${1:-$runtime_root/backups/latest}"
restore_database="ski_restore_check"

if [[ ! -f "$backup_directory/database.dump" || ! -f "$backup_directory/SHA256SUMS" ]]; then
  echo "Kein vollstaendiges Backup gefunden: $backup_directory" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a

if [[ "$restore_database" == "$POSTGRES_DB" ]]; then
  echo "Die Testdatenbank darf nicht der Produktivdatenbank entsprechen." >&2
  exit 1
fi

(
  cd "$backup_directory"
  sha256sum --check SHA256SUMS
)

compose=(docker compose --env-file "$environment_file" -f "$repo_dir/compose.pi.yaml")

cleanup_database() {
  "${compose[@]}" exec -T database \
    dropdb --if-exists --force --username "$POSTGRES_USER" "$restore_database" >/dev/null
}
trap cleanup_database EXIT

cleanup_database
"${compose[@]}" exec -T database \
  createdb --username "$POSTGRES_USER" "$restore_database"
"${compose[@]}" exec -T database \
  pg_restore --exit-on-error --no-owner --no-privileges \
    --username "$POSTGRES_USER" --dbname "$restore_database" \
  <"$backup_directory/database.dump"

count_query="SELECT sort || ':' || label || '=' || amount FROM (
  SELECT 1 AS sort, 'documents' AS label, count(*) AS amount FROM source_documents
  UNION ALL SELECT 2, 'imports', count(*) FROM extraction_imports
  UNION ALL SELECT 3, 'athletes', count(*) FROM athletes
  UNION ALL SELECT 4, 'runs', count(*) FROM run_results
  UNION ALL SELECT 5, 'submissions', count(*) FROM predictor_submissions
) AS counts ORDER BY sort"

production_counts="$("${compose[@]}" exec -T database \
  psql --tuples-only --no-align --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --command "$count_query")"
restore_counts="$("${compose[@]}" exec -T database \
  psql --tuples-only --no-align --username "$POSTGRES_USER" --dbname "$restore_database" \
    --command "$count_query")"

if [[ "$production_counts" != "$restore_counts" ]]; then
  echo "Wiederhergestellte Datenmengen weichen ab." >&2
  echo "Produktiv:" >&2
  echo "$production_counts" >&2
  echo "Wiederherstellung:" >&2
  echo "$restore_counts" >&2
  exit 1
fi

echo "Wiederherstellung erfolgreich geprueft:"
echo "$restore_counts"
