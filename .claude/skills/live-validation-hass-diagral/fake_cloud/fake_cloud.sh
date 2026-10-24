#!/usr/bin/env bash
# Start, stop and inspect the fake Diagral cloud used for live validation.
#
#   fake_cloud.sh up       build and start the container, install the redirect,
#                          write the marker — then restart Home Assistant
#   fake_cloud.sh down     remove the marker and the redirect, stop the
#                          container — then restart Home Assistant
#   fake_cloud.sh status   show what is in place
#   fake_cloud.sh logs     follow the fake cloud's log
#
# Runs on the Docker host. The Home Assistant devcontainer is found by image.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="diagral-fake-cloud"
PORT="${FAKE_CLOUD_PORT:-8099}"
HA_IMAGE_PATTERN="${HA_IMAGE_PATTERN:-vsc-home-assistant-dev}"
HA_CONFIG="${HA_CONFIG:-/workspaces/home-assistant-dev/config}"
HA_PYTHON="${HA_PYTHON:-/home/vscode/.local/ha-venv/bin/python}"
MARKER="$HA_CONFIG/.diagral_fake_cloud"
# Address of the fake cloud as seen from the Home Assistant container.
FAKE_URL="${FAKE_URL:-http://host.docker.internal:$PORT}"

ha_container() {
  local id
  id="$(docker ps --format '{{.ID}} {{.Image}}' | awk -v p="$HA_IMAGE_PATTERN" '$2 ~ p {print $1; exit}')"
  [[ -n "$id" ]] || { echo "No running container matches '$HA_IMAGE_PATTERN'" >&2; exit 1; }
  echo "$id"
}

site_packages() {
  docker exec "$1" "$HA_PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'
}

up() {
  local ha sp
  ha="$(ha_container)"
  sp="$(site_packages "$ha")"

  docker build -q -t "$NAME" "$HERE" >/dev/null
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" -p "$PORT:8099" "$NAME" >/dev/null
  echo "container   $NAME started on :$PORT"

  docker cp "$HERE/diagral_fake_cloud_redirect.py" "$ha:$sp/diagral_fake_cloud_redirect.py"
  docker exec -u root "$ha" sh -c "echo 'import diagral_fake_cloud_redirect' > '$sp/diagral_fake_cloud_redirect.pth'"
  echo "redirect    installed in $sp"

  docker exec "$ha" sh -c "echo '$FAKE_URL' > '$MARKER'"
  echo "marker      $MARKER -> $FAKE_URL"
  echo
  # Read back what is really in place: a truncated run can stop before the marker
  status
  echo
  echo "Restart Home Assistant for the redirect to take effect."
}

down() {
  local ha sp
  ha="$(ha_container)"
  sp="$(site_packages "$ha")"

  docker exec "$ha" rm -f "$MARKER"
  echo "marker      removed"
  docker exec -u root "$ha" rm -f "$sp/diagral_fake_cloud_redirect.pth" "$sp/diagral_fake_cloud_redirect.py"
  echo "redirect    removed"
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  echo "container   $NAME removed"
  echo
  echo "Restart Home Assistant so pydiagral talks to the real cloud again."
}

status() {
  local ha sp
  ha="$(ha_container)"
  sp="$(site_packages "$ha")"

  if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
    echo "container   running on :$PORT"
  else
    echo "container   not running"
  fi
  if docker exec "$ha" test -f "$sp/diagral_fake_cloud_redirect.pth"; then
    echo "redirect    installed"
  else
    echo "redirect    not installed"
  fi
  if docker exec "$ha" test -f "$MARKER"; then
    echo "marker      present -> $(docker exec "$ha" cat "$MARKER")"
  else
    echo "marker      absent"
  fi
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  logs) docker logs -f "$NAME" ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
