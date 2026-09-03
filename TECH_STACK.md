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
- 每日新词/复习词额度分开设置，复习优先于新词；复习池内部按到期日推送（逾期最久的先出，同一天到期的再按熟悉度从低到高）；还有到期词没复习完时不发新词
- 新词池按 `##` 章节分组轮转：以当天已学新词数对非空章节数取模作游标，每次取该章节里排最前的未学词，使各章节轮流出词，而不是学完一个章节才轮到下一个
- 熟悉度满格（Level 5）可选择「斩」掉，标记为 mastered 后永久退出队列

## 客户端状态
- `localStorage` 记录「今日已取消额度限制」的标记，用于「继续学习」功能，不经过后端持久化
