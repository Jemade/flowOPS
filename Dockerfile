FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Upgrade pip and install uv for fast and reliable dependency resolution
RUN pip install --no-cache-dir --upgrade pip uv

# Copy project files into container
COPY . .

# Install FlowOps package and dependencies
RUN uv pip install --system --no-cache .

# Create non-root user for security
RUN useradd -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
