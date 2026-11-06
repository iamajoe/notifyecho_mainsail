set shell := ["bash", "-euo", "pipefail", "-c"]

# List available recipes
default:
    @just --list

# Run the full unit and integration test suite
test:
    python3 -m unittest discover -s tests -v

# Run the settings UI locally with mocked Moonraker endpoints
dev port="8000":
    python3 scripts/dev_server.py --port {{port}}

# Lint Python, JavaScript and shell assets
lint:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v ruff >/dev/null 2>&1; then
        ruff check .
    else
        echo "ruff not installed; skipping Python lint"
    fi
    python3 -m compileall -q moonraker_component tests scripts
    if command -v node >/dev/null 2>&1; then
        node --check moonraker_component/notifyecho/static/app.js
    else
        echo "node not installed; skipping JavaScript check"
    fi
    bash -n install.sh
    bash -n uninstall.sh
    if command -v shellcheck >/dev/null 2>&1; then
        shellcheck --severity=error install.sh uninstall.sh
    else
        echo "shellcheck not installed; skipping shell lint"
    fi

# Run lint and tests
check: lint test

# Build a distributable archive and verify the installer
build:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 -m unittest tests.test_installer -v
    rm -rf dist
    mkdir -p dist/notifyecho_mainsail
    cp -R install.sh uninstall.sh README.md moonraker_component dist/notifyecho_mainsail/
    find dist/notifyecho_mainsail -name __pycache__ -type d -prune -exec rm -rf {} +
    find dist/notifyecho_mainsail -name '*.pyc' -delete
    tar -czf dist/notifyecho_mainsail.tar.gz -C dist notifyecho_mainsail
    rm -rf dist/notifyecho_mainsail
    echo "Built dist/notifyecho_mainsail.tar.gz"
