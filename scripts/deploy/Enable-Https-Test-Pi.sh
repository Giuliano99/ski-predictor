#!/usr/bin/env bash
set -Eeuo pipefail

repo_dir="${SKI_PREDICTOR_REPO:-/home/pi/ski-predictor}"
runtime_root="${SKI_PREDICTOR_RUNTIME:-/srv/ski-predictor}"
service_user="${SUDO_USER:-pi}"
environment_file="$runtime_root/config/runtime.env"
marker_file="$runtime_root/config/public-https-enabled"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bitte mit sudo ausfuehren: sudo $0" >&2
  exit 1
fi
if [[ ! -f "$environment_file" || ! -f "$repo_dir/compose.https-test.yaml" ]]; then
  echo "HTTPS-Testkonfiguration fehlt." >&2
  exit 1
fi

set_environment() {
  local name="$1"
  local value="$2"
  if grep -q "^${name}=" "$environment_file"; then
    sed -i "s|^${name}=.*|${name}=${value}|" "$environment_file"
  else
    printf '%s=%s\n' "$name" "$value" >>"$environment_file"
  fi
}

set_environment SKI_AUTH_REQUIRED 1
set_environment SKI_SECURE_COOKIES 1
set_environment SKI_BIND_ADDRESS 127.0.0.1
touch "$marker_file"
chown "$service_user:$service_user" "$marker_file"
chmod 0640 "$environment_file" "$marker_file"

compose=(docker compose --env-file "$environment_file" -f "$repo_dir/compose.pi.yaml" -f "$repo_dir/compose.https-test.yaml")
sudo -u "$service_user" "${compose[@]}" pull tunnel
sudo -u "$service_user" "${compose[@]}" up -d --force-recreate app tunnel

public_url=""
for _ in $(seq 1 30); do
  public_url="$(sudo -u "$service_user" "${compose[@]}" logs --no-color tunnel 2>&1 \
    | sed -nE 's|.*(https://[a-z0-9-]+\.trycloudflare\.com).*|\1|p' | tail -n 1)"
  if [[ -n "$public_url" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "$public_url" ]]; then
  echo "Der Tunnel laeuft, aber die oeffentliche URL wurde noch nicht gemeldet." >&2
  echo "Abruf: docker compose --env-file $environment_file -f $repo_dir/compose.pi.yaml -f $repo_dir/compose.https-test.yaml logs tunnel" >&2
  exit 1
fi

echo "HTTPS-Testzugang ist aktiv: $public_url/login/"
echo "Die URL aendert sich, wenn der Tunnel-Container neu erstellt wird."
