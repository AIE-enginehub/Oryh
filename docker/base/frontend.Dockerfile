FROM node:22-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./

RUN npm ci \
    && sha256sum package-lock.json > /oryh-frontend-package-lock.sha256
