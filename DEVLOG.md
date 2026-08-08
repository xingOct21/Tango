# DEVLOG

## v2.2 — 2026-08-08

### 已完成（已推送 `c4a3d51`）
- 新增英语答辩问答本 `word_en.md`，结构为「问题 / 英文答案 / 中文答案」，问题与答案均中英对照，段落用字面量 `\n` 分隔，前端 `renderText()` 渲染为换行
- UI 加入「日语 / English」单词本切换，选择存 `localStorage`；答辩本在翻牌前只显示问题，翻牌后同时显示英文答案与中文
- `parser.parse_words(book)` 按 `book` 参数读取 `word.md` 或 `word_en.md`；`/api/next`、`/api/review_today` 接受 `book` 查询参数
- 新增 `CLAUDE.md` 项目约定：日语本写入后自动查重（重复则删本次写入项并报告，同形异性词不算重复）、英语本中英自动补全、中译英需用简单易懂的词与语法
- 补全 `word.md` 105 条缺失读音/释义，删除 5 条重复占位行（提交 `f6667b4`）

### 每日额度按单词本分离
日语本与英语本的每日新词/复习额度、当日计数、学习进度全部独立，互不干扰。

- **`app.py`** —— 新增 `resolve_book()` 与 `get_limit(key, book)`；`get_progress` / `get_today_new_count` / `get_today_review_count` / `save_progress` 全部按 `book` 过滤或写入。五个路由（`/api/settings`、`/api/next`、`/api/review`、`/api/mastery`、`/api/review_today`）均从 query 或 body 取 `book` 并透传
- **额度键名** —— 由全局的 `new_words_limit` 改为分书的 `new_words_limit_{book}`。日语本在分书键缺失时回落到旧全局键，保证老用户原有设置不丢
- **`schema.sql`** —— 新增 v2.2 迁移段：`word_progress` 增 `book TEXT NOT NULL DEFAULT 'jp'`（存量行自动归日语本）、`(book, last_reviewed)` 复合索引、四个分书额度键（`_jp` 的值从旧全局键复制）。迁移幂等，可重复执行
- **`index.html`** —— 六处请求携带 `currentBook`；设置弹窗标题区分「每日设置 · 日语 / · English」，保存后自动刷新统计行

### 验证
- `app.py` 语法检查通过；grep 确认无遗漏的无参调用
- 模板渲染通过，六处 `book` 传递点逐一核对
- 迁移已在 Supabase SQL Editor 执行：`SELECT book, count(*) FROM word_progress GROUP BY book` 仅返回 `jp` 一行，确认存量进度全部正确归属日语本，无数据丢失

### 清理
- 删除 v1.0 遗留的孤儿键 `daily_limit`（v2.0 拆分新词/复习额度后即无代码读取；同名字符串仅作为 `/api/next` 的响应原因，与该表行无关）
- 无后缀的 `new_words_limit` / `review_words_limit` 暂时保留作回滚备份，待新版本线上稳定后再删

## v2.1 — 2026-07-19

### 修复
- 修复新词分类轮询失效的问题：`/api/next` 之前每次请求都重新计算轮询列表、只取第一个，导致轮询永远从文档里排最前的分类（如"名词"）出词，实际上要把该分类学完才会轮到下一个。现在改用当天已学新词数 `today_new_count` 对当前非空分类数取模，作为跨请求的轮询游标，确保各分类真正轮流出现

### 验证
- 用离线测试脚本（内存假 Supabase 客户端 + 虚构测试词，不连接真实数据库）跑通了斩词功能全流程：打分升级 → 满级弹出确认 → 调用斩词接口 → 数据库标记 mastered → 之后无论是否到期都不再出现；并做了反向验证确认测试本身有效

## v2.0 — 2026-07-09

### 已完成
- 新词/复习词每日额度分开设置，复习优先于新词
- 每个词记录累计学习次数（`review_count`），用于区分"今天是新学还是复习"
- 斩词：熟悉度满格时可选择永久退场，不再出现
- 继续学习：今日额度用完后可取消限制，继续学完当天已到期的词
- 自由复习：完成后可回顾今天学过的词，不影响 SRS 进度

---

## v1.0 — 2026-06-29

### 已完成
- 基于 SRS 算法的翻牌式复习（不会 / 模糊 / 记住了，间隔 1→3→7→14→30 天）
- 每日复习量上限，UI 内可直接设置
- 进度云端持久化（Supabase PostgreSQL）
- 自动部署（GitHub → Render）
- 自定义词源（Markdown 文件）
- 熟悉度可视化（橙点进度条）

---

## 未来功能

### 多词库切换（v2.2 部分实现）
- ~~UI 添加词库选择器~~ 已实现为「日语 / English」tab
- ~~支持多个 Markdown 数据源文件~~ 已实现 `word.md` / `word_en.md`
- `word_progress` 表新增区分字段（实现时定名为 `book`），各词库进度与额度独立记录 —— **进行中，见 v2.2「进行中」**
- 后续可继续扩展的场景：数学公式/定理、法律条文、游戏台词、任何需要记忆的内容

### 统计面板
- 今日/本周/本月复习量图表
- 各熟悉度等级分布
- 连续打卡天数

### 词条管理
- 直接在 UI 里增删改词条，不需要手动编辑 Markdown 再 push
- 支持给词条添加备注/例句

### 导入功能
- 从 CSV / Anki 导出文件导入词条
