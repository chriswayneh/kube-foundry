FROM nginx:1.31.6-alpine3.24 AS assets
WORKDIR /site
COPY index.html app.js styles.css ./

FROM nginx:1.31.6-alpine3.24 AS runtime
# Refresh this runtime library for the image vulnerability gate; retain non-root execution.
RUN apk upgrade --no-cache libexpat
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=assets --chown=101:101 /site/ /usr/share/nginx/html/
USER 101:101
EXPOSE 8080
