FROM python:3.12-slim

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir --requirement ./backend/requirements.txt
COPY alembic.ini .
COPY backend ./backend
COPY pipeline ./pipeline
COPY scripts ./scripts

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
