#!/bin/sh
set -eu

style="${NGINX_URI_STYLE:-prefix}"
case "$style" in
  prefix)
    edge='location ~ ^/(?<edge_width>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])x(?<edge_height>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])/(?<edge_image_path>.+)$ {'
    internal='location ~ ^/(?<width>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])x(?<height>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])/(?<image_path>.+)$ {'
    ;;
  suffix)
    edge='location ~ ^/(?<edge_image_path>.+)/_resize/(?<edge_width>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])x(?<edge_height>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])$ {'
    internal='location ~ ^/(?<image_path>.+)/_resize/(?<width>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])x(?<height>[1-9][0-9]?[0-9]?|1[0-9][0-9][0-9]|20[0-3][0-9]|204[0-8])$ {'
    ;;
  *)
    echo "NGINX_URI_STYLE must be prefix or suffix" >&2
    exit 1
    ;;
esac

config=/etc/nginx/nginx.conf
if grep -q '__EDGE_URI_LOCATION__' "$config"; then
  sed "s#__EDGE_URI_LOCATION__#$edge#; s#__INTERNAL_URI_LOCATION__#$internal#" "$config" > /run/nginx/nginx.conf
  exec "$@" -c /run/nginx/nginx.conf
fi

# Helm mounts a fully rendered config; its uriStyle value is authoritative.
exec "$@"
