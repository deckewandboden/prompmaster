FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend /app
RUN python -m compileall -q /app
RUN addgroup --system app && adduser --system --ingroup app app && chown -R app:app /app
USER app
CMD ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--threads","2","--timeout","60","--access-logfile","-","--error-logfile","-"]
