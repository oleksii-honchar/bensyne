# Racochu — NestJS CLI server for semantic content chunking.
# Mirrors apps/bensyne-mcp/Dockerfile structure: single-stage build, explicit
# base image, EXPOSE + ENV block, HEALTHCHECK (bensyne uses curl against its
# HTTP /health endpoint; racochu is a file-watcher CLI with no HTTP server, so
# the healthcheck verifies the built entrypoint loads without crashing).
FROM node:26-slim

WORKDIR /app

# native-machine-id is a native module (node-gyp) — needs python3 + build
# toolchain during `npm ci`. Installed before copying manifests so the layer
# stays cached across dependency changes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first for better caching
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

# Copy application source and build
COPY . .
RUN npm run build

# Create data directory (watched vault + SQLite tracker live here)
RUN mkdir -p /data/racochu

EXPOSE 3000

ENV NODE_ENV=production
ENV DATA_DIR=/data/racochu
ENV LOG_LEVEL=INFO

# tsc emits with the src/ prefix (outDir ./dist + include src/**/*), so the
# entrypoint is dist/src/main.js — not dist/main.js.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD node -e "require('./dist/src/main.js')" || exit 1

CMD ["node", "dist/src/main.js"]
