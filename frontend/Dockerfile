# ── Build stage ──
FROM node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci && npm cache clean --force
COPY . .
RUN npm run build

# ── Runtime stage ──
FROM node:20-alpine AS runtime
WORKDIR /app

RUN addgroup -S aegis && adduser -S aegis -G aegis

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/public ./public 2>/dev/null || true
COPY --from=builder /app/next.config.js ./

USER aegis
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

CMD ["npm", "start"]