FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir wikimore

EXPOSE 8109

CMD ["wikimore"]