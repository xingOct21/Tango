# Tech Stack

## 前端
- 原生 HTML / CSS / JavaScript（无框架）
- 响应式布局，兼容手机和桌面
- `static/drill.js` —— 本轮练习队列的纯逻辑（不碰 DOM / 网络 / 额度）。浏览器里当普通
  `<script>` 加载，Node 里可 `require`，因此测试不需要打包器，项目保持零构建步骤

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
- 本轮练习队列（drill）：当天点了「不认识」/「模糊」的词在本轮内随机重现，答对才放走。
  「不认识」需答对 2 次、重现间隔 2~3 张；「模糊」答对 1 次、间隔 4~6 张；连续 3 次没答对
  强制放走（否则记不住的词会让本轮永远结束不了）。每出一张牌，队列整体前进一格，有到期的
  就优先出练习卡，没有才去问后端要词
- **熟悉度只由该词当天首次点击决定**：练习卡不调 `/api/review`，不写库、不计额度。因此
  反复练习既不会把一个词刷上去，也不会消耗当天的复习额度。整个机制纯前端，后端无感知

## 客户端状态
- `localStorage` 记录「今日已取消额度限制」的标记，用于「继续学习」功能，不经过后端持久化
- `localStorage` 按本存 `tango_drill_{book}`：本轮练习队列，形如
  `{ date: "YYYY-MM-DD", items: { 词: { word, kind, remaining, missStreak, countdown } } }`。
  `date` 不是今天就整个丢弃（「本轮」即「今天」）；读取时逐项校验形状，坏项丢弃并
  `console.warn`；读写抛异常时降级为空队列 / 纯内存，不让打分流程中断
