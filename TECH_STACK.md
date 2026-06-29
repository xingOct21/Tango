# Tech Stack

## 前端
- 原生 HTML / CSS / JavaScript（无框架）
- 响应式布局，兼容手机和桌面

## 后端
- Python 3 + Flask
- Gunicorn（生产环境 WSGI 服务器）

## 数据库
- Supabase（托管 PostgreSQL）
- Supabase Python SDK（REST API，无二进制依赖）

## 部署
- Render（免费 Web Service，GitHub 自动触发部署）

## 数据格式
- 词源：Markdown 表格（`.md` 文件，本地维护，随代码部署）
- 进度：PostgreSQL 表（`word_progress`、`app_settings`）

## 算法
- SRS（Spaced Repetition System）间隔重复
- 熟悉度 Level 0-5，对应复习间隔：0 / 1 / 3 / 7 / 14 / 30 天
- 每日优先推送熟悉度最低的到期词条
