FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Baked in at build time if set (Vite inlines import.meta.env.* into the bundle) —
# left unset by default so the app computes API_BASE at runtime from whatever
# hostname/IP the browser actually used to load the page (see src/App.jsx). Only
# pass this explicitly for a topology where that assumption doesn't hold (e.g. the
# API isn't on the same host:8000 the page was loaded from).
ARG VITE_API_BASE=
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
