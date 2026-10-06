FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl postgresql-client gettext && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade "setuptools>=78.1.1" \
    && pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend /app
RUN python manage.py compilemessages --verbosity 0
RUN python -m compileall -q /app
RUN addgroup --system app && adduser --system --ingroup app app && mkdir -p /app/staticfiles /app/exports && chown -R app:app /app
USER app
CMD ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--threads","2","--timeout","60","--no-control-socket","--access-logfile","-","--error-logfile","-"]