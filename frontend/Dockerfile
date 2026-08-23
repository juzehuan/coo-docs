FROM node:20-alpine AS build
WORKDIR /app
# 用 lockfile + npm ci 保证依赖树可复现（npm install 会解析浮动 semver，每次构建结果不同且不可审计）
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
