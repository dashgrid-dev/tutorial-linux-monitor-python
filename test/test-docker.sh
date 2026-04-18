#!/bin/bash
# Local test: run monitor.py in a python:3.12-slim Docker container against a
# Dashgrid server configured in config.test.yaml. Requires: docker.
# localhost inside the container is remapped to the machine host, so pointing
# api_host at a locally-running Dashgrid server works.
#
# Usage: bash test/test-docker.sh     (Ctrl-C to stop)

set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f config.test.yaml ]; then
  echo "Error: config.test.yaml not found in $(pwd)"
  echo "Copy the example and fill in your API key + bucket IDs:"
  echo "  cp config.test.yaml.example config.test.yaml"
  exit 1
fi

echo ">>> Running in docker (localhost -> host.docker.internal)..."
docker run --rm -it \
  -e DASHGRID_CONFIG=/monitor/test/config.test.yaml \
  -v "$PWD/..:/monitor" -w /monitor \
  python:3.12-slim \
  sh -c "pip install --quiet --disable-pip-version-check --root-user-action=ignore -r requirements.txt && exec python monitor.py"
