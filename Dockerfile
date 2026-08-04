FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/instance /app/static/uploads

EXPOSE 8000

CMD ["sh", "-c", "python -c 'from app import init_db; init_db()' && exec gunicorn --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
