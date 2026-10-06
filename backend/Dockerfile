FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

# Utilisateur sans privilèges pour exécuter l'API
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /code/models /code/media \
    && chown app:app /code/models

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]