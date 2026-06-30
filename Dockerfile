# --- Stage 1: build the Vite frontend ---
FROM node:20-alpine AS frontend
WORKDIR /build/app/page
COPY app/page/package*.json ./
RUN npm install
COPY app/page/ ./
RUN npm run build

# --- Stage 2: Python runtime serving API + built SPA ---
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Bring in the production build from the frontend stage.
COPY --from=frontend /build/app/page/dist ./app/page/dist

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
