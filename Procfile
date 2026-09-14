release: python store/manage.py migrate --noinput
web: python store/manage.py collectstatic --noinput && gunicorn config.wsgi --chdir store --bind 0.0.0.0:$PORT
worker: python store/manage.py process_order_jobs --loop
