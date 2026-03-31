#!/bin/bash
set -e

mkdir -p /app/logs /app/data

exec uvicorn web.app:app --host 0.0.0.0 --port 5035 --workers 1 --timeout-keep-alive 75
