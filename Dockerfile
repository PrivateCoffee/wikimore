FROM alpine:3.21

ENV APP_ENV=/opt/venv
ENV PATH="${APP_ENV}/bin:$PATH"

RUN apk add --no-cache py3-pip uwsgi-python3 && \
  python3 -m venv $APP_ENV

COPY . /app

RUN $APP_ENV/bin/pip install --no-cache-dir pip && \
  $APP_ENV/bin/pip install /app && \
  adduser -S -D -H wikimore

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

EXPOSE 8109

USER wikimore

ENTRYPOINT ["/entrypoint.sh"]
