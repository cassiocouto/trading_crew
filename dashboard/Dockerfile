# Multi-stage Dockerfile for the trading-crew Next.js dashboard.
#
# Stage 1 (deps):    installs npm dependencies.
# Stage 2 (builder): produces a standalone Next.js output bundle.
# Stage 3 (runtime): minimal Node image that runs the pre-built bundle.
#
# Build:
#   docker build -t trading-crew-dashboard:latest dashboard/
# Run:
#   docker run --rm -it -p 3000:3000 \
#     -e NEXT_PUBLIC_API_URL=http://api:8000 \
#     trading-crew-dashboard:latest

# --------------------------------------------------------------------------
# Stage 1 — dependency install
# --------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

# --------------------------------------------------------------------------
# Stage 2 — build
# --------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# output:standalone is set in next.config.ts so Next.js emits a self-contained
# server bundle without requiring a full node_modules tree at runtime.
RUN npm run build

# --------------------------------------------------------------------------
# Stage 3 — runtime
# --------------------------------------------------------------------------
FROM node:20-alpine AS runtime

LABEL org.opencontainers.image.title="trading-crew-dashboard" \
      org.opencontainers.image.description="Next.js dashboard for trading-crew" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid  1001 nextjs

# Copy the standalone output produced by `next build`
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

ENV PORT=3000 \
    NODE_ENV=production

EXPOSE 3000

CMD ["node", "server.js"]
