FROM alpine:3.22

ARG NGINX_CONFIG=nginx-edge.conf
RUN apk add --no-cache nginx nginx-mod-http-image-filter ca-certificates \
    && mkdir -p /run/nginx /var/cache/nginx/image \
    && chown -R nginx:nginx /var/cache/nginx

COPY ${NGINX_CONFIG} /etc/nginx/nginx.conf
EXPOSE 8080 8082
CMD ["nginx", "-g", "daemon off;"]
