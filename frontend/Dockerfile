ARG ORYH_FRONTEND_BASE=node:22-alpine
ARG ORYH_NGINX_BASE=nginxinc/nginx-unprivileged:1.28.1-alpine
FROM ${ORYH_FRONTEND_BASE} AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN if [ -f /oryh-frontend-package-lock.sha256 ]; then \
      sha256sum -c /oryh-frontend-package-lock.sha256; \
    else \
      npm ci; \
    fi

COPY . .
# Release tag stamped onto the login page; falls back to package.json version
# when unset (see vite.config.ts).
ARG ORYH_APP_VERSION
ENV ORYH_APP_VERSION=$ORYH_APP_VERSION
RUN npm run build

FROM ${ORYH_NGINX_BASE}

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html/console

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/_health || exit 1
