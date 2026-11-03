#!/usr/bin/env bash
#
# NotifyEcho Mainsail installer.
#
# Installs a Moonraker component and adds a "NotifyEcho" entry to Mainsail's
# sidebar. Settings are configured from that page, never from this script.
#
set -Eeuo pipefail

REPO_URL="${NOTIFYECHO_REPO_URL:-https://codeberg.org/iamajoe/notifyecho_mainsail.git}"
BRANCH="${NOTIFYECHO_BRANCH:-main}"
INSTALL_DIR="${NOTIFYECHO_INSTALL_DIR:-$HOME/notifyecho_mainsail}"
DATA_DIR="${NOTIFYECHO_DATA_DIR:-$HOME/printer_data}"
CONFIG_FILE="${NOTIFYECHO_CONFIG_FILE:-}"
NO_RESTART="${NOTIFYECHO_NO_RESTART:-0}"

info() { printf '[NotifyEcho] %s\n' "$*"; }
warn() { printf '[NotifyEcho] WARNING: %s\n' "$*" >&2; }
die() { printf '[NotifyEcho] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: install.sh [options]

Options:
  -d, --data-dir <path>   Moonraker data directory (default: ~/printer_data)
  -c, --config <path>     moonraker.conf path (default: <data-dir>/config/moonraker.conf)
      --install-dir <path> Where to clone the plugin (default: ~/notifyecho_mainsail)
      --repo-url <url>     Git repository URL
      --branch <name>      Git branch (default: main)
      --no-restart         Do not restart Moonraker
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--data-dir)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      DATA_DIR="$2"
      shift 2
      ;;
    -c|--config)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CONFIG_FILE="$2"
      shift 2
      ;;
    --install-dir)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      INSTALL_DIR="$2"
      shift 2
      ;;
    --repo-url)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      BRANCH="$2"
      shift 2
      ;;
    --no-restart)
      NO_RESTART=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1 (use --help)"
      ;;
  esac
done

command -v git >/dev/null 2>&1 || die "git is required."
command -v python3 >/dev/null 2>&1 || die "python3 is required."

if [[ -z "$CONFIG_FILE" ]]; then
  CONFIG_FILE="$DATA_DIR/config/moonraker.conf"
fi

if [[ ! -f "$CONFIG_FILE" ]]; then
  for candidate in \
    "$HOME/printer_data/config/moonraker.conf" \
    "$HOME/klipper_config/moonraker.conf" \
    "$HOME/moonraker.conf"; do
    if [[ -f "$candidate" ]]; then
      CONFIG_FILE="$candidate"
      break
    fi
  done
fi

[[ -f "$CONFIG_FILE" ]] || die "Could not find moonraker.conf. Use -c /path/to/moonraker.conf."
CONFIG_DIR="$(cd "$(dirname "$CONFIG_FILE")" && pwd)"
CONFIG_FILE="$CONFIG_DIR/$(basename "$CONFIG_FILE")"

install_or_update_repo() {
  if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Updating $INSTALL_DIR"
    git -C "$INSTALL_DIR" fetch --prune origin
    git -C "$INSTALL_DIR" checkout "$BRANCH"
    git -C "$INSTALL_DIR" pull --ff-only origin "$BRANCH"
    return
  fi

  if [[ -e "$INSTALL_DIR" ]]; then
    die "$INSTALL_DIR exists but is not a git repository. Move it away or use --install-dir."
  fi

  info "Cloning $REPO_URL to $INSTALL_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
}

find_python_components_dir() {
  local python_bin="$1"
  "$python_bin" - <<'PY' 2>/dev/null || true
import pathlib
import sys
try:
    import moonraker
except Exception:
    sys.exit(1)
print(pathlib.Path(moonraker.__file__).resolve().parent / "components")
PY
}

find_components_dir() {
  local candidate
  local service_python=""

  if command -v systemctl >/dev/null 2>&1; then
    service_python="$(systemctl cat moonraker 2>/dev/null | sed -n 's/^ExecStart=//p' | head -n 1 | awk '{print $1}')" || true
  fi

  for candidate in \
    "$HOME/moonraker/moonraker/components" \
    "$HOME/moonraker/components"; do
    if [[ -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  for python_bin in \
    "$service_python" \
    "$HOME/moonraker-env/bin/python" \
    "$HOME/klipper-env/bin/python" \
    "python3" \
    "/usr/bin/python3"; do
    [[ -n "$python_bin" ]] || continue
    command -v "$python_bin" >/dev/null 2>&1 || continue
    candidate="$(find_python_components_dir "$python_bin")"
    if [[ -n "$candidate" && -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

install_or_update_repo

SOURCE_DIR="$INSTALL_DIR/moonraker_component/notifyecho"
[[ -d "$SOURCE_DIR" ]] || die "Component not found at $SOURCE_DIR"

COMPONENTS_DIR="$(find_components_dir)" || die "Could not locate Moonraker's components directory."
info "Moonraker components: $COMPONENTS_DIR"

TARGET="$COMPONENTS_DIR/notifyecho"
if [[ -L "$TARGET" ]]; then
  rm -f "$TARGET"
elif [[ -e "$TARGET" ]]; then
  BACKUP="$TARGET.bak.$(date +%Y%m%d%H%M%S)"
  mv "$TARGET" "$BACKUP"
  warn "Existing notifyecho component moved to $BACKUP"
fi
ln -s "$SOURCE_DIR" "$TARGET"
info "Linked $TARGET -> $SOURCE_DIR"

if ! grep -qE '^\[notifyecho\]' "$CONFIG_FILE"; then
  cat >>"$CONFIG_FILE" <<'EOF'

[notifyecho]
# NotifyEcho Mainsail plugin. Configure it from the NotifyEcho entry in Mainsail.
EOF
  info "Added [notifyecho] to $CONFIG_FILE"
else
  info "[notifyecho] already present in $CONFIG_FILE"
fi

if grep -qE '^\[update_manager(\]| )' "$CONFIG_FILE"; then
  if ! grep -qE '^\[update_manager notifyecho\]' "$CONFIG_FILE"; then
    cat >>"$CONFIG_FILE" <<EOF

[update_manager notifyecho]
type: git_repo
channel: dev
path: $INSTALL_DIR
origin: $REPO_URL
primary_branch: $BRANCH
managed_services: moonraker
EOF
    info "Added [update_manager notifyecho] to $CONFIG_FILE"
  else
    info "[update_manager notifyecho] already present in $CONFIG_FILE"
  fi
else
  warn "No [update_manager] section found; skipping update-manager registration."
fi

THEME_DIR="$CONFIG_DIR/.theme"
NAVI_FILE="$THEME_DIR/navi.json"
mkdir -p "$THEME_DIR"

python3 - "$NAVI_FILE" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
href = "/server/notifyecho/ui"
entry = {
    "title": "NotifyEcho",
    "href": href,
    "target": "_self",
    "position": 95,
    "icon": (
        "M12,22A2,2 0 0,0 14,20H10A2,2 0 0,0 12,22"
        "M18,16V11C18,7.93 16.36,5.36 13.5,4.68V4"
        "A1.5,1.5 0 0,0 12,2.5A1.5,1.5 0 0,0 10.5,4V4.68"
        "C7.63,5.36 6,7.92 6,11V16L4,18V19H20V18L18,16Z"
    ),
}

items = []
if path.exists():
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise SystemExit(
            "Cannot update %s: invalid JSON (%s). Fix or remove the file, then rerun."
            % (path, exc)
        )
    if not isinstance(parsed, list):
        raise SystemExit(
            "Cannot update %s: expected a JSON array. Fix or remove the file, then rerun."
            % path
        )
    backup = path.with_name(path.name + ".bak")
    if not backup.exists():
        backup.write_text(raw, encoding="utf-8")
    items = [
        item
        for item in parsed
        if not (
            isinstance(item, dict)
            and str(item.get("href", "")).rstrip("/") == href.rstrip("/")
        )
    ]

items.append(entry)
path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
PY
info "Updated Mainsail navigation: $NAVI_FILE"

if [[ "$NO_RESTART" != "1" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    info "Restarting Moonraker"
    sudo systemctl restart moonraker
  else
    warn "systemctl not found; restart Moonraker manually."
  fi
fi

cat <<EOF

NotifyEcho installed.

Next steps:
  1. Open Mainsail.
  2. Click "NotifyEcho" in the sidebar (position 95).
  3. Add the NotifyEcho URL, project bearer token and workflow ID(s).
  4. Use "Verify" to confirm each token + workflow combination.
  5. Use "Send test" to send a real test event.

Config:     $CONFIG_FILE
Component:  $TARGET
Repository: $INSTALL_DIR
EOF
