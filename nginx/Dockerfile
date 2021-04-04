FROM nginx
ARG NGINX_CONF
RUN echo ${NGINX_CONF}
COPY ./${NGINX_CONF} /etc/nginx/conf.d/default.conf
