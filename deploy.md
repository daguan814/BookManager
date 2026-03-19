# BookManager 部署说明（单容器，Flask + Gunicorn，证书目录映射）

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

## 2. 运行方式说明
- 容器内使用 `gunicorn` 作为生产 WSGI 服务器。
- 证书继续保留在宿主机目录 `/vol2/1000/backup/证书文档/Nginx`，通过 `-v ...:/etc/nginx/ssl:ro` 只读映射到容器，不打包进镜像。
- 若映射后的证书文件存在（`APP_SSL_CERT_FILE`/`APP_SSL_KEY_FILE`）则启用 HTTPS，否则回退 HTTP。
- 可选调优环境变量：`GUNICORN_WORKERS`（默认 2）、`GUNICORN_THREADS`（默认 4）。
- Flask 负责页面/API 鉴权：浏览器走 session 登录，图片脚本走 `X-Bookmanager-Token`。
- 容器启动时使用 `--restart always`，宿主机重启后会自动拉起容器。

## 3. 首次部署 / 全量更新
在本机项目目录执行。此方案会把当前 Git `HEAD` 打包到服务器临时目录，删除旧容器和旧镜像后重新构建；证书不进入构建上下文，运行时直接挂载宿主机证书目录。

```powershell
$server="shuijing@shuijing.site"
$port=12222
$key="C:\Users\lu873\Documents\id_rsa_macos"
$tmp="/tmp/bookmanager-build"

git archive --format=tar HEAD | ssh -i $key -p $port $server "rm -rf $tmp && mkdir -p $tmp && tar -xf - -C $tmp"

ssh -i $key -p $port $server "cd $tmp && \
  echo 'Lhf@2001.' | sudo -S docker rm -f BookManager 2>/dev/null || true && \
  echo 'Lhf@2001.' | sudo -S docker rmi -f bookmanager:latest 2>/dev/null || true && \
  echo 'Lhf@2001.' | sudo -S docker build --no-cache -t bookmanager:latest . && \
  echo 'Lhf@2001.' | sudo -S docker run -d --name BookManager --restart always --network host \
    -e APP_HOST=0.0.0.0 -e APP_PORT=8081 \
    -e DB_HOST=127.0.0.1 -e DB_PORT=3306 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=bookmanager \
    -e APP_SECRET_KEY=bookmanager-change-this-secret \
    -e WEB_LOGIN_PASSWORD=sgxx \
    -e SCRIPT_API_TOKEN=bookmanager-script-token \
    -e APP_SSL_CERT_FILE=/etc/nginx/ssl/shuijing.site.pem \
    -e APP_SSL_KEY_FILE=/etc/nginx/ssl/shuijing.site.key \
    -v /vol2/1000/backup/证书文档/Nginx:/etc/nginx/ssl:ro \
    bookmanager:latest && \
  rm -rf $tmp"
```

## 4. 日常发布（推荐）
推荐重复上面的全量发布命令。服务器不保留源码目录，但证书目录仍保留在宿主机并通过 volume 映射，所以日常发布同样采用临时构建目录 + 运行时挂载证书的方式。

## 5. 检查命令
```bash
ssh -i C:/Users/lu873/Documents/id_rsa_macos -p 12222 shuijing@shuijing.site \
  "echo 'Lhf@2001.' | sudo -S docker ps --filter name=BookManager && \
   echo 'Lhf@2001.' | sudo -S docker logs --tail=120 BookManager && \
   curl -k https://127.0.0.1:8081/health"
```

## 6. 常见问题
- `8081 打不开`：确认容器日志里没有证书读取错误，并检查宿主机目录 `/vol2/1000/backup/证书文档/Nginx` 下存在 `shuijing.site.pem` / `shuijing.site.key`，且已正确映射到容器内 `/etc/nginx/ssl/`。
- `API 报错`：先看 `BookManager` 日志，再检查数据库连通性。
- `图片脚本 401`：检查容器里的 `SCRIPT_API_TOKEN` 是否和脚本端一致。
- 浏览器仍旧旧页面：强刷 `Ctrl+F5`。
