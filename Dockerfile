FROM alpine:3.22

ARG NGINX_CONFIG=nginx.conf
ARG NGINX_CACHE_VALIDITY=10m
ARG NGINX_MAX_CONCURRENT_IMAGE_REQUESTS=16

COPY ${NGINX_CONFIG} /etc/nginx/nginx.conf

RUN apk add --no-cache nginx nginx-mod-http-image-filter ca-certificates \
    && mkdir -p /run/nginx /var/cache/nginx/image \
    && chown -R nginx:nginx /var/cache/nginx \
    && sed -i "s/proxy_cache_valid 200 10m;/proxy_cache_valid 200 ${NGINX_CACHE_VALIDITY};/; s/limit_conn image_requests 16;/limit_conn image_requests ${NGINX_MAX_CONCURRENT_IMAGE_REQUESTS};/" /etc/nginx/nginx.conf

EXPOSE 80 443 8080
CMD ["nginx", "-g", "daemon off;"]
