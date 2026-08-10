#!/bin/sh
set -e

# Fix ownership of directories that may be mounted as tmpfs.
# The official nginx entrypoint normally does this, but we override it.
# Worker process runs as 'nginx' user (UID 101), needs write access to:
#   - /var/cache/nginx (client_temp, proxy_temp, fastcgi_temp, etc.)
#   - /var/run (pid file, sockets)
if [ -d /var/cache/nginx ]; then
    chown -R nginx:nginx /var/cache/nginx
fi
if [ -d /var/run ]; then
    chown -R nginx:nginx /var/run
fi
# Create nginx temp subdirs (client_temp etc.) if missing
nginx -T >/dev/null 2>&1 || true

# Substitute environment variables in nginx config template
if [ -f /etc/nginx/conf.d/default.conf.template ]; then
    envsubst '${TAM_NGINX_PORT} ${TAM_NGINX_SSL_PORT} ${TAM_BACKEND_PORT}' \
        < /etc/nginx/conf.d/default.conf.template \
        > /etc/nginx/conf.d/default.conf
    echo "nginx: config generated (HTTP: ${TAM_NGINX_PORT:-8080}, HTTPS: ${TAM_NGINX_SSL_PORT:-8443}, Backend: ${TAM_BACKEND_PORT:-8000})"
fi

nginx -t
echo "nginx: starting..."
exec nginx -g 'daemon off;'