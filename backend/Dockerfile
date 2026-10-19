FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Shell form (not exec-form array) so $PORT actually expands - Render
# sets PORT itself (default 10000) and routes to whatever port the
# container binds; 8000 is just the local-docker-compose fallback.
CMD uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}
