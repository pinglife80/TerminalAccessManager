# Frontend Builder - Builds React app and outputs to /app/dist
FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with retry logic
RUN npm ci --network-timeout=100000 || \
    npm install --network-timeout=100000 || \
    npm install --registry https://registry.npmmirror.com

# Copy source code
COPY . .

# Build the application (outputs to /app/dist)
RUN npm run build

# Backup build output before volume mount overrides it
RUN cp -r /app/dist /app/dist_backup

# Create non-root user for security
RUN adduser -D appuser && chown -R appuser:appuser /app

# Copy build files to volume on startup
# Volume is mounted at /app/dist, so we copy from the build stage backup
CMD ["sh", "-c", "if [ -d /app/dist_backup ]; then cp -r /app/dist_backup/* /app/dist/ && echo 'Frontend build copied to volume'; else echo 'No backup found, build may already be in volume'; fi"]
