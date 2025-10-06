FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends         ca-certificates         && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY web_admin.py /app/web_admin.py
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh

# Data directory holds token.json and state.json; credentials holds OAuth client json
VOLUME ["/app/data", "/app/credentials"]

CMD ["/app/start.sh"]
