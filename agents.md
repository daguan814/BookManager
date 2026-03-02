# BookManager AGENTS 指令

## 部署固定信息
- 部署服务器：`ssh.shuijing.site:12222`
- 服务器账号：`shuijing`
- SSH 私钥：`C:\Users\lu873\Documents\id_rsa_macos`
- 若需 sudo 密码：`Lhf@2001.`
- 项目部署目录：`/vol2/1000/backup/docker/bookmanager`
- Docker 根目录：`/vol2/1000/backup/docker`
- 文件传输方式：`sftp`

## 当前部署约定（已落地）
- 前端：`nginx` 容器，`HTTPS`，端口 `18080`
- 后端：`FastAPI` 容器，端口 `18081`
- 数据库：`127.0.0.1:3306`
- 证书目录（宿主机）：`/vol2/1000/backup/证书文档/Nginx`
- 已使用证书文件：`shuijing.site.pem`、`shuijing.site.key`

## Docker 编排
- 禁止使用：`docker compose` / `docker-compose`
- 必须使用：手动 `docker build` + `docker run`
- 容器约定：
  - `bookmanager-backend`（`--network host`，便于访问宿主机 MySQL）
  - `bookmanager-frontend`（`nginx:alpine`，挂载前端静态文件和 SSL 证书）

## FRP 约定
- `frpc` 配置文件：`/vol2/1000/backup/docker/frpc/frpc.ini`
- frps 服务器：`8.148.95.251`（仅作为 FRP 服务端，不作为项目部署 SSH 目标）
- 已配置转发：
  - `nas-book-18080` -> `192.168.100.109:18080`
  - `nas-book-18081` -> `192.168.100.109:18081`

## 常用运维命令
- 进入部署目录：
  - `cd /vol2/1000/backup/docker/bookmanager`
- 后端构建：
  - `sudo docker build -t bookmanager-backend:manual -f Dockerfile .`
- 启动后端：
  - `sudo docker rm -f bookmanager-backend || true`
  - `sudo docker run -d --name bookmanager-backend --restart unless-stopped --network host -e APP_HOST=0.0.0.0 -e APP_PORT=18081 -e DB_HOST=127.0.0.1 -e DB_PORT=3306 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=bookmanager bookmanager-backend:manual`
- 启动前端：
  - `sudo docker rm -f bookmanager-frontend || true`
  - `sudo docker run -d --name bookmanager-frontend --restart unless-stopped --network host -v /vol2/1000/backup/docker/bookmanager/frontend:/usr/share/nginx/html:ro -v /vol2/1000/backup/docker/bookmanager/deploy/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro -v /vol2/1000/backup/证书文档/Nginx:/etc/nginx/ssl:ro nginx:1.27-alpine`
- 查看状态：
  - `sudo docker ps`
  - `sudo docker logs -f bookmanager-backend`
  - `sudo docker logs -f bookmanager-frontend`
- 重启 FRPC（修改 frpc.ini 后）：
  - `sudo docker restart frpc`

## 执行要求
- 严格按以上目录、端口、证书路径执行。
- 新任务优先复用当前手动 Docker 方案，不要改成其他部署方式。
- 明确禁止使用 `docker compose`。
- 修改端口或证书文件名时，需同时更新：
  - `deploy/nginx/default.conf`
  - `/vol2/1000/backup/docker/frpc/frpc.ini`
