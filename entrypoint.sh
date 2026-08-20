#!/bin/sh
set -e

BIND_HOST="${WIKIMORE_HOST:-${HOST:-0.0.0.0}}"
BIND_PORT="${WIKIMORE_PORT:-${PORT:-8109}}"
BIND_SOCKET="${WIKIMORE_SOCKET:-${SOCKET:-}}"

if [ -n "$BIND_SOCKET" ]; then
    case "$BIND_SOCKET" in
        unix:*) BIND="$BIND_SOCKET" ;;
        *) BIND="unix:$BIND_SOCKET" ;;
    esac
else
    BIND="$BIND_HOST:$BIND_PORT"
fi

set -- --bind "$BIND" --worker-class gevent --access-logfile -

if [ -n "$WIKIMORE_WORKERS" ]; then
    set -- "$@" --workers "$WIKIMORE_WORKERS"
fi

if [ -n "$WIKIMORE_THREADS" ]; then
    set -- "$@" --threads "$WIKIMORE_THREADS"
fi

exec gunicorn "$@" wikimore.app:app
