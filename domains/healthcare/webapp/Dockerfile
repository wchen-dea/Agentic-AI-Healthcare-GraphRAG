FROM nginx:alpine
COPY shared_lib/webapp/nginx.conf /etc/nginx/conf.d/default.conf
COPY shared_lib/webapp/styles.css /usr/share/nginx/html/styles.css
COPY shared_lib/webapp/query-helpers.js /usr/share/nginx/html/query-helpers.js
COPY domains/healthcare/webapp/index.html /usr/share/nginx/html/index.html
COPY domains/healthcare/webapp/domain.js /usr/share/nginx/html/domain.js
