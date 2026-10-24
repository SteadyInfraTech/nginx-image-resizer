FROM alpine:3.22

ARG NGINX_CONFIG=nginx.conf
ARG NGINX_CACHE_VALIDITY=10m
ARG NGINX_MAX_CONCURRENT_IMAGE_REQUESTS=16
ARG NGINX_PUBLIC_HOST=localhost

COPY ${NGINX_CONFIG} /etc/nginx/nginx.conf

RUN apk add --no-cache nginx nginx-mod-http-image-filter ca-certificates \
    && mkdir -p /run/nginx /var/cache/nginx/image /var/lib/nginx/logs /var/lib/nginx/tmp \
    && chmod 755 /var/lib/nginx /var/lib/nginx/logs /var/lib/nginx/tmp \
    && ln -sf /dev/stderr /var/lib/nginx/logs/error.log \
    && chown -R nginx:nginx /var/cache/nginx \
    && if [ "${NGINX_CONFIG}" = "nginx-direct-tls.conf" ]; then \
         case "${NGINX_PUBLIC_HOST}" in ""|*[!A-Za-z0-9.-]*|.*|*.|*..*) echo "NGINX_PUBLIC_HOST must be a DNS hostname" >&2; exit 1 ;; esac; \
         sed -i "s/server_name _;/server_name ${NGINX_PUBLIC_HOST};/g" /etc/nginx/nginx.conf; \
       fi \
    && sed -i "s/proxy_cache_valid 200 10m;/proxy_cache_valid 200 ${NGINX_CACHE_VALIDITY};/; s/limit_conn image_requests 16;/limit_conn image_requests ${NGINX_MAX_CONCURRENT_IMAGE_REQUESTS};/" /etc/nginx/nginx.conf

EXPOSE 80 443 8080
CMD ["nginx", "-g", "daemon off;"]
