FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.29-alpine

ENV PLANNER_API_UPSTREAM=http://planner-backend:8080
ENV PORTAL_URL=http://portal.localhost:8088
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
