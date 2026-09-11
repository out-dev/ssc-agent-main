#!/bin/sh
set -eu

exec /opt/cognee-venv/bin/uvicorn cognee.api.client:app \
    --host "$HTTP_API_HOST" \
    --port "$HTTP_API_PORT"
