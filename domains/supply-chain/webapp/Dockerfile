FROM nginx:alpine
COPY infra/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY domains/supply-chain/webapp/styles.css /usr/share/nginx/html/styles.css
COPY domains/supply-chain/webapp/query-helpers.js /usr/share/nginx/html/query-helpers.js
COPY domains/supply-chain/webapp/index.html /usr/share/nginx/html/index.html
COPY domains/supply-chain/webapp/domain.js /usr/share/nginx/html/domain.js
