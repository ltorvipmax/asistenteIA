FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json .
RUN npm install

COPY . .

ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build:railway

FROM node:20-alpine
WORKDIR /app

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist

ENV PORT=3000

CMD ["sh", "-c", "npm run start"]