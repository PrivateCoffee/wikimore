FROM alpine:3.22

ENV PORT=8109

RUN apk add --no-cache py3-pip

COPY . /app

RUN pip install --no-cache-dir --break-system-packages /app[redis,gunicorn] && \
  adduser -S -D -H wikimore

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

EXPOSE 8109

USER wikimore

ENTRYPOINT ["/entrypoint.sh"]
