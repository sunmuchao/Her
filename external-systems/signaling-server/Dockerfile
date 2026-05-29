FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY signaling_server ./signaling_server

ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "-m", "signaling_server.server", "--host", "0.0.0.0", "--port", "8765"]