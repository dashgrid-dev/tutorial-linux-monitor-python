#!/bin/bash
# Installs the Dashgrid Python monitor as a systemd service.
# Expects: monitor.py, requirements.txt, config.yaml in this directory.
# Usage: sudo bash setup.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Error: run as root"; exit 1; fi

DIR=$(cd "$(dirname "$0")" && pwd)
[ -f "$DIR/monitor.py" ]       || { echo "Error: monitor.py not found in $DIR"; exit 1; }
[ -f "$DIR/requirements.txt" ] || { echo "Error: requirements.txt not found in $DIR"; exit 1; }
[ -f "$DIR/config.yaml" ]      || { echo "Error: config.yaml not found in $DIR"; exit 1; }
chmod 600 "$DIR/config.yaml"

PY=$(command -v python3 || true)
[ -n "$PY" ] || { echo "Error: python3 not found. Install python3 and python3-venv."; exit 1; }

echo ">>> Creating virtualenv at $DIR/.venv..."
"$PY" -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

echo ">>> Creating systemd service..."
cat > /etc/systemd/system/dashgrid-monitor.service << EOF
[Unit]
Description=Dashgrid Linux Monitor (Python)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$DIR/.venv/bin/python $DIR/monitor.py
WorkingDirectory=$DIR
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo ">>> Starting service..."
systemctl daemon-reload
systemctl enable --now dashgrid-monitor.service

echo ">>> Done!"
echo "Logs:   sudo journalctl -u dashgrid-monitor -f"
echo "Config: $DIR/config.yaml"
