# Stage 1: Build stage with compile dependencies
FROM python:3.11-alpine AS builder

WORKDIR /app

# Install system dependencies for building
RUN apk add --no-cache gcc g++ musl-dev libpq-dev freetds-dev unixodbc-dev \
    libffi-dev openssl-dev

# Create app user early and install packages to accessible location
RUN adduser -D app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage (minimal)
FROM python:3.11-alpine

WORKDIR /app

# Install only runtime dependencies
RUN apk add --no-cache libpq curl freetds unixodbc libstdc++ libffi openssl postgresql-client

# Configure FreeTDS ODBC driver
RUN echo "[FreeTDS]" >> /etc/odbcinst.ini && \
    echo "Description=FreeTDS Driver" >> /etc/odbcinst.ini && \
    echo "Driver=/usr/lib/libtdsodbc.so" >> /etc/odbcinst.ini && \
    echo "Setup=/usr/lib/libtdsodbc.so" >> /etc/odbcinst.ini

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

# Pre-create volume mount points with correct ownership.
# Docker named volumes copy content+perms from image ONLY on first mount,
# so we must ensure these dirs exist and are owned by app:app BEFORE USER directive.
RUN mkdir -p /var/log/tam && \
    mkdir -p /app/uploads/backups && \
    mkdir -p /app/uploads/branding && \
    chown -R app:app /var/log/tam /app/uploads

USER app

# Use ENV for configurable port (default: 8000)
ENV BACKEND_PORT=8000

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${BACKEND_PORT}/health || exit 1

# Run application (shell form to allow variable expansion)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${BACKEND_PORT}