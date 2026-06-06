# Stage 1: Build stage with compile dependencies
FROM python:3.11-alpine AS builder

WORKDIR /app

# Install system dependencies for building
RUN apk add --no-cache gcc musl-dev libpq-dev

# Create app user early and install packages to accessible location
RUN adduser -D app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage (minimal)
FROM python:3.11-alpine

WORKDIR /app

# Install only runtime dependencies
RUN apk add --no-cache libpq curl

# Create app user before copying packages
RUN adduser -D app

# Copy Python packages from builder to app user's home
COPY --from=builder /root/.local /home/app/.local
RUN chown -R app:app /home/app/.local
ENV PATH=/home/app/.local/bin:$PATH

# Copy application code
COPY . .

# Set ownership
RUN chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
