#!/bin/sh
set -e

# Fix ownership of mounted volumes so appuser can write
chown -R appuser:appuser /app/logs /app/data 2>/dev/null || true

# Drop privileges and exec the CMD as appuser
exec gosu appuser "$@"
