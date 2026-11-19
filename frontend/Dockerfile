FROM node:26-alpine
WORKDIR /app
COPY package.json ./
COPY src ./src
USER node
EXPOSE 3000
CMD ["node", "src/server.mjs"]
