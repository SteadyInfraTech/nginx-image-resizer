FROM nginx:1.30.6-alpine

ARG NGINX_CONFIG=nginx.conf
ARG NGINX_CACHE_VALIDITY=10m
ARG NGINX_MAX_CONCURRENT_IMAGE_REQUESTS=16
ARG NGINX_PUBLIC_HOST=localhost
ARG NGINX_ORIGIN_UPSTREAM=origin:8081

COPY ${NGINX_CONFIG} /etc/nginx/nginx.conf

RUN set -eu; \
    printf "%s" "${NGINX_MAX_CONCURRENT_IMAGE_REQUESTS}" | grep -Eq "^[1-9][0-9]*$" || { echo "NGINX_MAX_CONCURRENT_IMAGE_REQUESTS must be a positive integer" >&2; exit 1; }; \
    printf "%s" "${NGINX_CACHE_VALIDITY}" | grep -Eq "^[0-9]+(ms|s|m|h|d|w|M|y)$" || { echo "NGINX_CACHE_VALIDITY must be a single NGINX time value, e.g. 10m or 1s" >&2; exit 1; }; \
    printf "%s" "${NGINX_ORIGIN_UPSTREAM}" | grep -Eq "^[A-Za-z0-9.-]+:[0-9]{1,5}$" || { echo "NGINX_ORIGIN_UPSTREAM must be a hostname:port pair" >&2; exit 1; }; \
    apk add --no-cache ca-certificates; \
    mkdir -p /run/nginx /var/cache/nginx/image /var/lib/nginx/logs /var/lib/nginx/tmp; \
    chmod 755 /var/lib/nginx /var/lib/nginx/logs /var/lib/nginx/tmp; \
    ln -sf /dev/stderr /var/lib/nginx/logs/error.log; \
    chown -R nginx:nginx /var/cache/nginx; \
    test -r /usr/lib/nginx/modules/ngx_http_image_filter_module.so; \
    if [ "${NGINX_CONFIG}" = "nginx-direct-tls.conf" ]; then \
      case "${NGINX_PUBLIC_HOST}" in ""|*[!A-Za-z0-9.-]*|.*|*.|*..*) echo "NGINX_PUBLIC_HOST must be a DNS hostname" >&2; exit 1 ;; esac; \
      sed -i "s/server_name _;/server_name ${NGINX_PUBLIC_HOST};/g" /etc/nginx/nginx.conf; \
    fi; \
    sed -i "s/server origin:8081;/server ${NGINX_ORIGIN_UPSTREAM};/; s/proxy_cache_valid 200 10m;/proxy_cache_valid 200 ${NGINX_CACHE_VALIDITY};/; s/limit_conn image_requests 16;/limit_conn image_requests ${NGINX_MAX_CONCURRENT_IMAGE_REQUESTS};/" /etc/nginx/nginx.conf

EXPOSE 80 443 8080
CMD ["nginx", "-g", "daemon off;"]
