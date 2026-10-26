FROM postgres:18-alpine
# Restic and PostgreSQL CLI do not need the inherited libcurl library.
# Remove vulnerable CVE-2026-92392 instead of mixing in Alpine edge packages.
# Fail the image build unless the patched Brotli runtime is available.
RUN --mount=type=secret,id=pf_staging_ca,required=false \
    if [ -s /run/secrets/pf_staging_ca ]; then \
      cat /etc/ssl/cert.pem /run/secrets/pf_staging_ca > /tmp/pf-staging-ca-combined.pem; \
      export SSL_CERT_FILE=/tmp/pf-staging-ca-combined.pem; \
      export GIT_SSL_CAINFO=/tmp/pf-staging-ca-combined.pem; \
      export CURL_CA_BUNDLE=/tmp/pf-staging-ca-combined.pem; \
      trap 'rm -f /tmp/pf-staging-ca-combined.pem' EXIT; \
    fi; \
    apk add --no-cache bash restic ca-certificates tzdata su-exec 'brotli-libs>=1.2.1-r0' \
    && apk del --no-cache libcurl \
    && ! apk info -e libcurl \
    && restic version \
    && pg_dump --version \
    && psql --version \
    && rm -f /usr/local/bin/gosu
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
