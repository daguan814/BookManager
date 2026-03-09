# BookManager
图书管理系统（Flask 单体应用，前后端不分离）

## 当前结构

- `main.py`：Flask 入口（同时提供页面和 API）
- `Controller/`：Flask 蓝图
- `Service/`：模型、Schema、业务逻辑、外部书籍 API
- `db/`：数据库连接与初始化脚本
- `config.py`：配置读取
- `frontend/`：由 Flask 直接托管的页面与静态资源

## 功能（保持不变）

- 扫码/输入 ISBN 查询书籍信息（外部 API）
- 网页调用手机摄像头扫码 ISBN
- 入库/出库确认与库存更新
- 后台管理：图书管理、库存流水、导出 CSV

## 1. 初始化数据库

数据库名：`bookmanager`

```bash
mysql -u root -p < db/init_db.sql
```

## 2. 本地启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

默认地址：`https://127.0.0.1:8081`（若证书不存在会回退为 `http://127.0.0.1:8081`）

## 3. 环境变量

- `APP_HOST` 默认 `0.0.0.0`
- `APP_PORT` 默认 `8081`
- `DB_HOST` 默认 `127.0.0.1`
- `DB_PORT` 默认 `3306`
- `DB_USER` 默认 `root`
- `DB_PASSWORD` 默认 `Lhf134652`
- `DB_NAME` 默认 `bookmanager`
- `APP_SSL_CERT_FILE` 默认 `/etc/nginx/ssl/shuijing.site.pem`
- `APP_SSL_KEY_FILE` 默认 `/etc/nginx/ssl/shuijing.site.key`
