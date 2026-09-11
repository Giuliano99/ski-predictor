#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
service_user="${SUDO_USER:-pi}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo $0" >&2
  exit 1
fi

if [[ ! -f "$repo_dir/compose.pi.yaml" ]]; then
  echo "compose.pi.yaml fehlt in $repo_dir" >&2
  exit 1
fi

install -d -m 0750 -o "$service_user" -g "$service_user" \
  "$runtime_root/config" \
  "$runtime_root/documents" \
  "$runtime_root/backups" \
  "$runtime_root/state/config/weekends" \
  "$runtime_root/state/data/questions" \
  "$runtime_root/state/data/extractions" \
  "$runtime_root/state/data/submissions/inbox" \
  "$runtime_root/state/data/submissions/processed" \
  "$runtime_root/state/data/result-lists/processed" \
  "$runtime_root/state/apps/web/src/data" \
  "$runtime_root/state/output/audit" \
  "$runtime_root/state/output/reports"

seed_directory() {
  local source="$1"
  local destination="$2"
  if [[ -d "$source" && -z "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    cp -a "$source/." "$destination/"
  fi
}

seed_directory "$repo_dir/config/weekends" "$runtime_root/state/config/weekends"
seed_directory "$repo_dir/data/questions" "$runtime_root/state/data/questions"
seed_directory "$repo_dir/apps/web/src/data" "$runtime_root/state/apps/web/src/data"
seed_directory "$repo_dir/output" "$runtime_root/state/output"

cat >"$runtime_root/config/local-storage.json" <<'JSON'
{
  "schemaVersion": 1,
  "provider": "local-folder",
  "root": "/data/documents"
}
JSON

environment_file="$runtime_root/config/runtime.env"
if [[ ! -f "$environment_file" ]]; then
  database_password="$(openssl rand -hex 24)"
  cat >"$environment_file" <<EOF
POSTGRES_DB=ski_data
POSTGRES_USER=ski_app
POSTGRES_PASSWORD=$database_password
SKI_RUNTIME_ROOT=$runtime_root
SKI_BIND_ADDRESS=0.0.0.0
SKI_PORT=4175
EOF
fi

touch "$runtime_root/config/auto-deploy-enabled"
chown -R "$service_user:$service_user" "$runtime_root"
chmod 0640 "$environment_file" "$runtime_root/config/local-storage.json"

install -m 0644 "$repo_dir/scripts/deploy/systemd/ski-predictor-update.service" /etc/systemd/system/ski-predictor-update.service
install -m 0644 "$repo_dir/scripts/deploy/systemd/ski-predictor-update.timer" /etc/systemd/system/ski-predictor-update.timer
systemctl daemon-reload

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  up -d --build --remove-orphans

sudo -u "$service_user" docker compose \
  --env-file "$environment_file" \
  -f "$repo_dir/compose.pi.yaml" \
  exec -T app python services/api/src/database_cli.py import-existing

systemctl enable --now ski-predictor-update.timer

echo "Ski Predictor ist unter http://$(hostname -I | awk '{print $1}'):4175/tippspiel/ erreichbar."
