FROM postgres:18-alpine
RUN apk add --no-cache bash restic ca-certificates tzdata su-exec
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod 0755 /usr/local/bin/backup.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
