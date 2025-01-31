#!/bin/sh
args="--plugin python3 \
	--http-socket 0.0.0.0:$PORT \
	--master \
	--module wikimore.app:app \
	-H /opt/venv"

if [ "$UWSGI_PROCESSES" ]
then
	args="$args --processes $UWSGI_PROCESSES"
fi

if [ "$UWSGI_THREADS" ]
then
	args="$args --threads $UWSGI_THREADS"
fi

exec /usr/sbin/uwsgi $args
