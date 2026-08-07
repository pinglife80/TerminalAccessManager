#!/bin/sh
set -e

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