#!/bin/sh
# Substitute only ${API_HOST} so nginx variables ($host, $remote_addr) are preserved.
envsubst '${API_HOST}' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
