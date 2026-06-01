# Stage 1: Frontend build
FROM node:18-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --legacy-peer-deps
COPY web/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements-lock.txt ./
RUN pip install --no-cache-dir -r requirements-lock.txt || pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY prompts/ ./prompts/
COPY VERSION ./
COPY pyproject.toml ./

# Copy frontend build
COPY --from=frontend-builder /app/web/.next ./web/.next
COPY --from=frontend-builder /app/web/public ./web/public
COPY --from=frontend-builder /app/web/package*.json ./web/
COPY --from=frontend-builder /app/web/next.config.js ./web/

# Create necessary directories
RUN mkdir -p data output logs

EXPOSE 8000 3000

# Default command runs backend API
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
