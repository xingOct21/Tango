# Tango — 日语单词记忆卡片

基于间隔重复算法（SRS）的日语单词复习工具，支持云端部署，手机电脑均可使用。

## 功能

- 翻牌式复习，按掌握程度自动调整复习频率
- 每日单词量可在页面内自由设置
- 进度云端保存，换设备不丢失

## 部署教程

### 1. Fork 仓库

点击右上角 **Fork**，复制到你自己的 GitHub 账号。

### 2. 准备数据库（Supabase）

1. 注册 [supabase.com](https://supabase.com)，新建一个 Project
2. 进入 **SQL Editor**，执行 `schema.sql` 里的内容（建表）
3. 去 **Settings → API**，记下：
   - **Project URL**（如 `https://xxx.supabase.co`）
   - **service_role** 那行的 secret key

### 3. 部署应用（Render）

1. 注册 [render.com](https://render.com)，新建 **Web Service**
2. 连接你 Fork 的 GitHub 仓库
3. 配置如下：
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. 在 **Environment Variables** 里添加：
   - `SUPABASE_URL` = 第 2 步的 Project URL
   - `SUPABASE_KEY` = 第 2 步的 service_role key
5. 点击 Deploy，完成后会得到一个 `https://xxx.onrender.com` 的链接

### 4. 替换单词表

编辑 `word.md`，格式如下：

```markdown
## 分类名称

| 日语 | 假名 | 中文 |
|------|------|------|
| 食べる | たべる | 吃 |
| 飲む | のむ | 喝 |
```

改完后 push 到 GitHub，Render 会自动重新部署。

## 使用说明

- 打开网页，点击**翻牌**查看答案
- 根据掌握程度点击「不会 / 模糊 / 记住了」
- 点击右上角 ⚙ 可设置每日单词量
- 熟悉度越高（橙点越多），复习间隔越长（最长 30 天）
