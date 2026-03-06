FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY assets/*.ttf assets/

RUN pip install --no-cache-dir . && mkdir -p /app/data

ENV PYTHONPATH=/app/src

CMD ["python", "-m", "bot"]
