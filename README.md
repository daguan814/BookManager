# BookManager
图书管理系统（前后端分离，FastAPI + 静态前端）

## 当前结构

- `main.py`：FastAPI 入口（一键启动后端）
- `Controller/`：路由蓝图（APIRouter）
- `Service/`：模型、Schema、业务逻辑、外部书籍 API
- `db/`：数据库连接
- `config/`：配置读取
- `frontend/`：前端页面
- `init_db.sql`：MySQL 初始化脚本

## 功能（V1）

- 扫码/输入 ISBN 查询书籍信息（外部 API）
- 网页调用手机摄像头扫码 ISBN
- 入库/出库确认弹窗，可修改数量
- 管理界面：3 标签页（入库/出库、库存总览含流水、图书管理）
- 前后端分离（前端静态服务 + 后端 API）

## 1. 初始化数据库

数据库名：`bookmanager`

```bash
mysql -u root -p < init_db.sql
```

## 2. 使用 conda 启动后端（单命令）

```bash
conda create -n bookmanager python=3.11 -y
conda activate bookmanager
pip install -r requirements.txt
```

数据库与端口配置统一在 `config/config.py` 里修改：

- `db_host`
- `db_port`（当前为 `13306`）
- `db_user`
- `db_password`
- `db_name`

一键启动后端：

```bash
python main.py
```

接口文档：`http://127.0.0.1:8000/docs`

## 3. 启动前端（独立）

```bash
cd frontend
python -m http.server 5173
```

浏览器打开：`http://127.0.0.1:5173`

前端默认请求后端：`http://127.0.0.1:8000`（可在 `frontend/app.js` 修改 `API_BASE`）。

说明：

- 前端框架资源（Vue、Element Plus、html5-qrcode）已下载到 `frontend/vendor/`，默认本地加载，不依赖公网 CDN。
