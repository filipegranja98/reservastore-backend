#!/bin/sh
set -eu
if [ "${DJANGO_MIGRATE_ON_START:-false}" = "true" ]; then
    python manage.py migrate --noinput
fi
python manage.py collectstatic --noinput
exec gunicorn reservastoresupa.core.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --access-logfile - --error-logfile -
