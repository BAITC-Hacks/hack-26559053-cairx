FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY BackendAI/requirements.txt /app/BackendAI/requirements.txt
RUN pip install --no-cache-dir -r /app/BackendAI/requirements.txt

COPY BackendAI/ /app/BackendAI/
COPY static/ /app/static/

WORKDIR /app/BackendAI
EXPOSE 8000
CMD ["python", "run.py"]
