#!/bin/sh
UWSGI_HOST="${WIKIMORE_HOST:-${HOST:-0.0.0.0}}"
UWSGI_PORT="${WIKIMORE_PORT:-${PORT:-8109}}"
UWSGI_SOCKET="${WIKIMORE_SOCKET:-${SOCKET:-}}"

args="--plugin python3 --master --module wikimore.app:app -H /opt/venv"
if [ -n "$UWSGI_SOCKET" ]; then
    case "$UWSGI_SOCKET" in
         unix:*) ;;
         /*) UWSGI_SOCKET="unix:$UWSGI_SOCKET" ;;
    esac
    args="$args --http-socket $UWSGI_SOCKET"
else
    args="$args --http-socket $UWSGI_HOST:$UWSGI_PORT"
fi

if [ "$UWSGI_PROCESSES" ]; then
    args="$args --processes $UWSGI_PROCESSES"
fi
if [ "$UWSGI_THREADS" ]; then
    args="$args --threads $UWSGI_THREADS"
fi
exec /usr/sbin/uwsgi $args