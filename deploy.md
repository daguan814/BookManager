# BookManager 部署说明（单容器 + 宿主机 MySQL）

## 1. 固定信息
- 服务器：`shuijing.site:12222`
- 用户：`shuijing`
- 私钥：`C:\Users\lu873\Documents\id_rsa_macos`
- sudo 密码：`Lhf@2001.`
- 证书目录：`/vol2/1000/backup/证书文档/Nginx`
- 对外端口：`8081`（HTTPS）
- 数据库：`127.0.0.1:3306`
- 容器名：`BookManager`
- Web 登录密码环境变量：`WEB_LOGIN_PASSWORD`
- 脚本专用 Token 环境变量：`SCRIPT_API_TOKEN`

## 2. 这次修复了什么
- 应用启动前会等待数据库就绪，不再因为 MySQL 比 Web 慢几秒启动就直接炸掉。
- 应用启动时会自动 `create_all`，首次部署或空库时不容易因为表不存在直接失败。
- `/health` 现在会顺带检查数据库连通性，容器健康状态更可信。
- 增加了 `Dockerfile` 健康检查。
- 数据继续放在宿主机 MySQL，`BookManager` 容器本身保持无状态，重建容器不会影响数据库数据。

## 3. 推荐运行方式（更稳）
- 容器内继续使用 `gunicorn` 作为生产 WSGI 服务器。
- 继续使用宿主机 MySQL：`127.0.0.1:3306`。
- 容器只承载 Web 应用，数据库不放进容器里，所以重建 `BookManager` 容器不会丢数据。
- 证书继续保留在宿主机，通过 `./certs:/etc/nginx/ssl:ro` 或服务器绝对路径映射到容器，不打包进镜像。
- 若映射后的证书文件存在（`APP_SSL_CERT_FILE`/`APP_SSL_KEY_FILE`）则启用 HTTPS，否则回退 HTTP。
- Flask 负责页面/API 鉴权：浏览器走 session 登录，图片脚本走 `X-Bookmanager-Token`。
- 容器启动使用 `--restart unless-stopped`，容器异常退出、Docker 重启、宿主机重启后都会自动恢复。

## 4. 首次部署 / 全量更新
在本机项目目录执行。继续沿用你原来的 `git archive -> 服务器临时目录 -> build -> run` 思路，只是把环境变量抽到 `.env`，并保留宿主机 MySQL。

```powershell
$server="shuijing@shuijing.site"
$port=12222
$key="C:\Users\lu873\Documents\id_rsa_macos"
$tmp="/tmp/bookmanager-build"

git archive --format=tar HEAD | ssh -i $key -p $port $server "rm -rf $tmp && mkdir -p $tmp && tar -xf - -C $tmp"

ssh -i $key -p $port $server "cat > $tmp/.env <<'EOF'
APP_HOST=0.0.0.0
APP_PORT=8081
APP_SECRET_KEY=bookmanager-change-this-secret
WEB_LOGIN_PASSWORD=sgxx
SCRIPT_API_TOKEN=bookmanager-script-token
SESSION_DAYS=7
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=Lhf134652
DB_NAME=bookmanager
DB_CONNECT_RETRIES=30
DB_CONNECT_RETRY_DELAY=3
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
APP_SSL_CERT_FILE=/etc/nginx/ssl/shuijing.site.pem
APP_SSL_KEY_FILE=/etc/nginx/ssl/shuijing.site.key
EOF"

ssh -i $key -p $port $server "cd $tmp && \
  echo 'Lhf@2001.' | sudo -S docker rm -f BookManager 2>/dev/null || true && \
  echo 'Lhf@2001.' | sudo -S docker rmi -f bookmanager:latest 2>/dev/null || true && \
  echo 'Lhf@2001.' | sudo -S docker build --no-cache -t bookmanager:latest . && \
  echo 'Lhf@2001.' | sudo -S docker run -d --name BookManager --restart unless-stopped --network host --env-file $tmp/.env \
    -v /vol2/1000/backup/证书文档/Nginx:/etc/nginx/ssl:ro \
    bookmanager:latest"
```

说明：
- 因为数据库在宿主机 MySQL，真正需要持久化的是 MySQL 本身；`BookManager` 容器随时删掉重建都没关系。
- `--network host` 下，容器里访问 `127.0.0.1:3306` 就是宿主机 MySQL。
- 证书仍然直接挂宿主机目录，不进镜像。

## 5. 日常发布
- 推荐重复上面的发布命令。
- 如果只是改代码，直接重新 `build + run` 当前单容器即可，不影响宿主机 MySQL 数据。

## 6. 检查命令
```bash
ssh -i C:/Users/lu873/Documents/id_rsa_macos -p 12222 shuijing@shuijing.site \
  "echo 'Lhf@2001.' | sudo -S docker ps --filter name=BookManager && \
   echo 'Lhf@2001.' | sudo -S docker logs --tail=120 BookManager && \
   curl -k https://127.0.0.1:8081/health || curl http://127.0.0.1:8081/health"
```

## 7. 常见问题
- `Web 容器一直重启`：大概率是宿主机 MySQL 没起来、账号密码不对，或 `.env` 里的 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD` 填错；先看 `docker logs BookManager`。
- `8081 打不开`：先确认 `docker ps` 里 `BookManager` 正常运行，再检查证书路径映射是否正确。
- `健康检查失败`：现在 `/health` 会检查数据库，所以如果 MySQL 不可用会直接返回 `503`，这是预期行为。
- `重建后数据没了`：如果真发生，问题不在应用容器，而在宿主机 MySQL 本身；当前方案里应用容器不存数据库数据。
- `图片脚本 401`：检查 `.env` 里的 `SCRIPT_API_TOKEN` 是否和脚本端一致。
