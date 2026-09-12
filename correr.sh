#!/usr/bin/env bash
# Corre la app desde el código, sin compilar. Es lo que quieres al desarrollar.
set -e
cd "$(dirname "$0")"
exec ./.venv/bin/python -m vortex_studio "$@"
