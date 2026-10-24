FROM alpine:3.22

ARG NGINX_CONFIG=nginx.conf
ARG NGINX_CACHE_VALIDITY=10m

COPY ${NGINX_CONFIG} /etc/nginx/nginx.conf

RUN apk add --no-cache nginx nginx-mod-http-image-filter ca-certificates \
    && mkdir -p /run/nginx /var/cache/nginx/image \
    && chown -R nginx:nginx /var/cache/nginx \
    && sed -i "s/proxy_cache_valid 200 10m;/proxy_cache_valid 200 ${NGINX_CACHE_VALIDITY};/" /etc/nginx/nginx.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
