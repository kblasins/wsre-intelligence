# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

COPY package.json package-lock.json* ./
# Use ci for reproducible builds from lockfile
RUN npm ci --prefer-offline

COPY . .
RUN npm run build

# ── Stage 2: serve via nginx ───────────────────────────────────────────────────
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="ws-hub-frontend"
LABEL org.opencontainers.image.description="White Star Market Intelligence Hub — frontend"

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/health || exit 1
