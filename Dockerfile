FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json .
RUN npm install --production

FROM node:20-alpine AS runner
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY index.js .
COPY package.json .
USER appuser
EXPOSE 4567
HEALTHCHECK --interval=30s --timeout=5s CMD wget -qO- http://localhost:4567/health || exit 1
CMD ["node", "index.js"]
