# syntax=docker/dockerfile:1.7
# AURA OFFICE AI — frontend image (Next.js).
# Build context: repository root.

ARG NODE_VERSION=22

FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# --- Development: source bind-mounted by docker-compose -------------------------------
FROM node:${NODE_VERSION}-alpine AS dev
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

# --- Production build ----------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Used by the Next.js rewrite only when the app is served without Nginx in front.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./
RUN npm run build

FROM node:${NODE_VERSION}-alpine AS prod
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup --system --gid 1001 aura && adduser --system --uid 1001 --ingroup aura aura
COPY --from=builder --chown=aura:aura /app/.next/standalone ./
COPY --from=builder --chown=aura:aura /app/.next/static ./.next/static
COPY --from=builder --chown=aura:aura /app/public ./public
USER aura
EXPOSE 3000
CMD ["node", "server.js"]
