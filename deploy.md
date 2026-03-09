# BookManager 部署说明（单容器，Flask + Gunicorn）

## 1. 固定信息
- 服务器：`shuijing.site:12222`
- 用户：`shuijing`
- 私钥：`C:\Users\Administrator\Documents\id_rsa_macos`
- sudo 密码：`Lhf@2001.`
- 服务器项目目录：`/vol2/1000/backup/docker/bookmanager`
- 证书目录：`/vol2/1000/backup/证书文档/Nginx`
- 对外端口：`8081`（HTTPS）
- 数据库：`127.0.0.1:3306`
- 容器名：`BookManager`

## 2. 运行方式说明
- 容器内使用 `gunicorn` 作为生产 WSGI 服务器。
- 若容器内存在证书文件（`APP_SSL_CERT_FILE`/`APP_SSL_KEY_FILE`）则启用 HTTPS，否则回退 HTTP。
- 可选调优环境变量：`GUNICORN_WORKERS`（默认 2）、`GUNICORN_THREADS`（默认 4）。

## 3. 首次部署 / 全量更新
在本机项目目录执行：

```powershell
$server="shuijing@shuijing.site"
$port=12222
$key="C:\Users\Administrator\Documents\id_rsa_macos"
$remote="/vol2/1000/backup/docker/bookmanager"

ssh -i $key -p $port $server "mkdir -p $remote"

sftp -i $key -P $port $server << 'SFTP'
cd /vol2/1000/backup/docker/bookmanager
put -r Controller
put -r Service
put -r db
put -r frontend
put Dockerfile
put main.py
put config.py
put requirements.txt
put deploy.md
put README.md
SFTP

ssh -i $key -p $port $server "cd $remote && \
  sudo docker build -t bookmanager:latest . && \
  sudo docker rm -f BookManager 2>/dev/null || true && \
  sudo docker run -d --name BookManager --restart unless-stopped --network host \
    -e APP_HOST=0.0.0.0 -e APP_PORT=8081 \
    -e DB_HOST=127.0.0.1 -e DB_PORT=3306 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=bookmanager \
    -e APP_SSL_CERT_FILE=/etc/nginx/ssl/shuijing.site.pem \
    -e APP_SSL_KEY_FILE=/etc/nginx/ssl/shuijing.site.key \
    -v /vol2/1000/backup/证书文档/Nginx:/etc/nginx/ssl:ro \
    bookmanager:latest"
```

## 4. 日常发布（推荐）
只上传改动文件后重建并重启：

```bash
ssh -i C:/Users/Administrator/Documents/id_rsa_macos -p 12222 shuijing@shuijing.site \
  "cd /vol2/1000/backup/docker/bookmanager && \
   sudo docker build -t bookmanager:latest . && \
   sudo docker rm -f BookManager 2>/dev/null || true && \
   sudo docker run -d --name BookManager --restart unless-stopped --network host \
     -e APP_HOST=0.0.0.0 -e APP_PORT=8081 \
     -e DB_HOST=127.0.0.1 -e DB_PORT=3306 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=bookmanager \
     -e APP_SSL_CERT_FILE=/etc/nginx/ssl/shuijing.site.pem \
     -e APP_SSL_KEY_FILE=/etc/nginx/ssl/shuijing.site.key \
     -v /vol2/1000/backup/证书文档/Nginx:/etc/nginx/ssl:ro \
     bookmanager:latest"
```

如需同步 `frpc` 端口到 `8081`，可执行：

```bash
ssh -i C:/Users/Administrator/Documents/id_rsa_macos -p 12222 shuijing@shuijing.site \
  "sudo docker run --rm -v /vol2/1000/backup/docker/frpc:/work alpine:3.20 sh -lc \"sed -i 's/\[nas-book-18080\]/[nas-book-8081]/; s/local_port = 18080/local_port = 8081/; s/remote_port = 18080/remote_port = 8081/' /work/frpc.ini\" && \
   sudo docker restart frpc"
```

## 5. 检查命令
```bash
ssh -i C:/Users/Administrator/Documents/id_rsa_macos -p 12222 shuijing@ssh.shuijing.site \
  "sudo docker ps --filter name=BookManager && sudo docker logs --tail=120 BookManager && curl -k https://127.0.0.1:8081/health"
```

## 6. 常见问题
- `8081 打不开`：确认容器日志里没有证书读取错误，且证书文件名为 `shuijing.site.pem` / `shuijing.site.key`。
- `frpc 访问不到`：把 `frpc.toml`（或对应 ini 配置）里指向 BookManager 的本地端口同步改成 `8081`，重启 `frpc` 后再检查连通性。
- `API 报错`：先看 `BookManager` 日志，再检查数据库连通性。
- 浏览器仍旧旧页面：强刷 `Ctrl+F5`。
