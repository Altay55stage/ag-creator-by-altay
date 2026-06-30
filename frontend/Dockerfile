FROM node:22-alpine

WORKDIR /app

COPY package*.json .
RUN npm ci

COPY . .
RUN adduser -D appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
