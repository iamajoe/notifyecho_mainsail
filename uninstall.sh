#!/usr/bin/env bash
#
# NotifyEcho Mainsail uninstaller.
#
set -Eeuo pipefail

INSTALL_DIR="${NOTIFYECHO_INSTALL_DIR:-$HOME/notifyecho_mainsail}"
DATA_DIR="${NOTIFYECHO_DATA_DIR:-$HOME/printer_data}"
CONFIG_FILE="${NOTIFYECHO_CONFIG_FILE:-}"
NO_RESTART="${NOTIFYECHO_NO_RESTART:-0}"
PURGE=0

info() { printf '[NotifyEcho] %s\n' "$*"; }
warn() { printf '[NotifyEcho] WARNING: %s\n' "$*" >&2; }
die() { printf '[NotifyEcho] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: uninstall.sh [options]

Options:
  -d, --data-dir <path>   Moonraker data directory (default: ~/printer_data)
  -c, --config <path>     moonraker.conf path (default: <data-dir>/config/moonraker.conf)
      --install-dir <path> Plugin checkout (default: ~/notifyecho_mainsail)
      --purge              Remove the plugin checkout too
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
    --purge)
      PURGE=1
      shift
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
    candidate="$("$python_bin" - <<'PY' 2>/dev/null || true
import pathlib
import sys
try:
    import moonraker
except Exception:
    sys.exit(1)
print(pathlib.Path(moonraker.__file__).resolve().parent / "components")
PY
)"
    if [[ -n "$candidate" && -d "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

COMPONENTS_DIR="$(find_components_dir || true)"
TARGET=""
if [[ -n "$COMPONENTS_DIR" ]]; then
  TARGET="$COMPONENTS_DIR/notifyecho"
  if [[ -L "$TARGET" ]]; then
    LINK_TARGET="$(readlink "$TARGET")"
    if [[ "$LINK_TARGET" == "$INSTALL_DIR/moonraker_component/notifyecho" ]]; then
      rm -f "$TARGET"
      info "Removed component link $TARGET"
    else
      warn "Leaving $TARGET alone; it points to $LINK_TARGET"
    fi
  elif [[ -e "$TARGET" ]]; then
    warn "Leaving $TARGET alone; it is not a symlink."
  fi
else
  warn "Could not locate Moonraker's components directory."
fi

python3 - "$CONFIG_FILE" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
headers = {"[notifyecho]", "[update_manager notifyecho]"}
out = []
skipping = False

for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        skipping = stripped in headers
    if not skipping:
        out.append(line)

# Collapse trailing blank lines and runs of more than two blank lines.
cleaned = []
blank_run = 0
for line in out:
    if line.strip():
        blank_run = 0
        cleaned.append(line)
    else:
        blank_run += 1
        if blank_run <= 2:
            cleaned.append(line)

while cleaned and not cleaned[-1].strip():
    cleaned.pop()

path.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
PY
info "Removed NotifyEcho sections from $CONFIG_FILE"

NAVI_FILE="$CONFIG_DIR/.theme/navi.json"
if [[ -f "$NAVI_FILE" ]]; then
  python3 - "$NAVI_FILE" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
href = "/server/notifyecho/ui"
raw = path.read_text(encoding="utf-8")
try:
    items = json.loads(raw)
except ValueError:
    raise SystemExit(
        "Cannot update %s: invalid JSON. Leaving the navigation entry alone." % path
    )
if not isinstance(items, list):
    raise SystemExit(
        "Cannot update %s: expected a JSON array. Leaving the navigation entry alone." % path
    )

items = [
    item
    for item in items
    if not (
        isinstance(item, dict)
        and str(item.get("href", "")).rstrip("/") == href.rstrip("/")
    )
]
path.write_text(json.dumps(items, indent=2) + "\n", encoding="utf-8")
PY
  info "Removed NotifyEcho from $NAVI_FILE"
fi

if [[ "$NO_RESTART" != "1" ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    info "Restarting Moonraker"
    sudo systemctl restart moonraker
  else
    warn "systemctl not found; restart Moonraker manually."
  fi
fi

if [[ "$PURGE" == "1" ]]; then
  rm -rf "$INSTALL_DIR"
  info "Removed $INSTALL_DIR"
fi

cat <<EOF

NotifyEcho uninstalled.

The plugin settings remain in Moonraker's database namespace "notifyecho".
Remove them manually if you want a clean wipe.
EOF
