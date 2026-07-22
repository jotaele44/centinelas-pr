#!/usr/bin/env sh
set -eu
python3 scripts/offline_operator.py export
python3 scripts/offline_operator.py dashboard
python3 scripts/offline_operator.py package
python3 scripts/offline_operator.py validate
