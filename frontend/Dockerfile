# Build from the REPOSITORY ROOT: docker build -f frontend/Dockerfile .
FROM node:22-alpine AS deps
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
WORKDIR /usr/src/app
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY frontend/package.json ./frontend/
COPY packages/ui/package.json ./packages/ui/
RUN pnpm install --frozen-lockfile

FROM node:22-alpine AS build
RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
WORKDIR /usr/src/app
COPY --from=deps /usr/src/app/node_modules ./node_modules
COPY --from=deps /usr/src/app/frontend/node_modules ./frontend/node_modules
COPY --from=deps /usr/src/app/packages/ui/node_modules ./packages/ui/node_modules
COPY . .
# NEXT_PUBLIC_* is INLINED at build time, so the API host is baked here and each
# environment builds its own image.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN pnpm --filter frontend build

FROM node:22-alpine AS runtime
WORKDIR /usr/src/app/frontend
ENV NODE_ENV=production PORT=3001 HOSTNAME=0.0.0.0
COPY --from=build /usr/src/app/frontend/.next/standalone /usr/src/app
COPY --from=build /usr/src/app/frontend/.next/static ./.next/static
USER node
EXPOSE 3001
CMD ["node", "server.js"]
