# Frontend Builder - Builds React app and outputs to /app/dist
FROM node:18-alpine

WORKDIR /app

ARG VERSION
ENV VITE_APP_VERSION=${VERSION}

COPY VERSION ./VERSION

COPY frontend/package*.json ./

# Sync version from VERSION file to package.json (ensures consistency)
RUN sed -i "s/\"version\": \"[0-9]*\.[0-9]*\.[0-9]*\"/\"version\": \"$(cat VERSION | tr -d '[:space:]')\"/" package.json

RUN npm ci --network-timeout=100000 || \
    npm install --network-timeout=100000 || \
    npm install --registry https://registry.npmmirror.com

COPY frontend/. .

RUN npm run build

RUN cp -r /app/dist /app/dist_backup

RUN adduser -D appuser && chown -R appuser:appuser /app

CMD ["sh", "-c", "if [ -d /app/dist_backup ]; then cp -r /app/dist_backup/* /app/dist/ && echo 'Frontend build copied to volume'; else echo 'No backup found, build may already be in volume'; fi"]