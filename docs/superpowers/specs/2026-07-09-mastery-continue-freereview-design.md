# 斩词 / 继续学习 / 自由复习 — 设计文档

**日期**: 2026-07-09
**状态**: 已确认，待实现
**依赖**: 建立在 [新词/复习词分离系统设计](./2026-07-09-new-word-system-design.md) 之上（需要 `review_count` 字段已存在）

## 背景

这是原「新词系统」之外，用户追加的 3 个相关功能：

1. 词记熟了（level 达到 5）可以选择「斩」掉，永远不再出现
2. 每日额度用完后，可以选择继续学习当天已到期但还没学的词
3. 学完之后，还想自由复习今天学过的词，纯回顾，不影响 SRS 进度

三者共享同一个「完成界面」的入口。

## 功能 1：斩词（mastery）

### 数据模型

```sql
ALTER TABLE word_progress ADD COLUMN IF NOT EXISTS mastered BOOLEAN NOT NULL DEFAULT false;
```

### 触发流程

1. `/api/review` 计算出 `new_level` 后，若 `new_level == 5`，响应里附加 `reached_max_level: true`（其余情况为 `false`）
2. 前端收到 `reached_max_level: true` 时，弹确认框：「这个词已经记得很牢固了，要斩掉吗？」，两个选项：
   - **斩** → 调用 `POST /api/mastery`，body `{jp}`，把该词的 `mastered` 设为 `true`
   - **不斩** → 不调用任何接口，词保持在 level 5，按现有 30 天间隔正常循环。下次它再到期并且再次被评为「记住了」（level 仍是 5），会再次弹出确认框
3. 斩后的词：`mastered = true` 的行在 `/api/next` 的 `review_due` 查询里被过滤掉，此后不会再出现在任何队列（新词队列本来就不会含有已有进度行的词，无需额外处理）
4. 不提供撤销 UI（明确不做）

### 前端改动

- `score()` 函数：调用 `/api/review` 后检查 `reached_max_level`，为 `true` 时插入确认弹窗逻辑（复用现有 `#modal-overlay` 结构或新增一个轻量确认框），确认后再调用 `/api/mastery`，最后统一 `loadNext()`

## 功能 2：继续学习（当日额度用完后）

### 状态存储

- 纯前端本地状态，`localStorage` 键如 `tango_extended_date`，值为日期字符串（`YYYY-MM-DD`）
- 点击「继续学习」时写入今天的日期
- 每次请求 `/api/next` 前，前端检查 `localStorage` 中的日期是否等于今天，是则在请求上带 `?extended=1`

### 后端行为

- `/api/next` 读取 `extended` 参数（默认 `0`）
- 为 `1` 时，跳过 `remaining_new <= 0` / `remaining_review <= 0` 的额度判断，只要 `review_due` / `new_words` 池子里还有词，就继续正常按「复习优先于新词」的顺序出题
- 额度判断被跳过后，`done` 的唯一可能原因是 `all_done`（两个池子都真正空了）

### 前端行为

- 完成界面（不论 `reason` 是 `daily_limit` 还是 `all_done`）固定显示「继续学习」按钮
- 点击后：写入 `localStorage` 标记 → 调用 `loadNext()`（这次会带 `extended=1`）→ 继续学习直到再次进入完成界面（此时因为已经带着 `extended=1`，`reason` 必然是 `all_done`）
- 次日日期变化后，旧的 `localStorage` 标记不再匹配当天日期，`extended` 参数自然不再发送，额度恢复正常

## 功能 3：自由复习（今日已学词，不影响 SRS）

### 新接口

`GET /api/review_today` — 返回 `last_reviewed == 今天` 的所有词（今天学过的新词 + 复习过的旧词都算），保持 `word.md` 中的原始顺序：

```json
[{"jp": "...", "kana": "...", "zh": "...", "section": "..."}, ...]
```

不需要额外的日期/额度信息，因为这是固定列表，不受每日上限影响。

### 前端行为

- 完成界面固定显示「复习」按钮（和「继续学习」并列）
- 点击后：一次性拉取 `/api/review_today` 的列表，进入纯前端翻牌模式
  - 翻牌、看答案、评分按钮（不会/模糊/记住了）UI 和正常学习模式一致
  - 区别：点击评分按钮**只是切到列表里的下一张卡**，不调用 `/api/review`，不写库，不影响 `level`/`next_review`/`review_count`/`mastered` 任何字段
- 列表翻完后显示「复习完了」，回到完成界面

## 完成界面整合逻辑

「继续学习」和「复习」两个按钮**始终同时出现**在完成界面上，互不排斥：

- 点「继续学习」，学到 `extended` 模式下的 `all_done` 后，回到完成界面（两个按钮还在）
- 点「复习」，翻完今日已学列表后，回到完成界面（两个按钮还在）
- 可以来回切换点击，不限制顺序或次数

## 明确不做的事（Out of scope）

- 斩词无撤销/查看列表功能
- 「继续学习」不做次数累加（不是每点一次 +N，而是一次性取消当天限制直到真正学完）
- 「继续学习」不提前拉取未来日期（`next_review` 还没到的）的词，只处理今天已到期的词
- 「复习」模式的评分完全不落库，纯前端状态
- `extended` 状态不做跨设备同步（只存 `localStorage`，符合用户确认的"不需要这么严格"）

## 与新词系统设计的交互

- `mastered = true` 的词在 `/api/next` 的 `review_due` 筛选里被排除，这一步在 [新词系统设计](./2026-07-09-new-word-system-design.md) 描述的"复习优先于新词"选词逻辑**之前**先过滤
- `extended=1` 只影响额度判断（第 2 步 `remaining_review`/`remaining_new` 的比较），不影响选词优先级本身
- `/api/review_today` 复用 `last_reviewed` 字段，与新词系统里"今日新词数/复习词数"统计的字段完全一致，无需新增列
