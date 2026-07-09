# 新词/复习词分离系统 — 设计文档

**日期**: 2026-07-09
**状态**: 已确认，待实现

## 背景

现有系统只有一个「每日总数上限」（`daily_limit`），新词和到期复习词混在同一个队列里，按熟悉度等级排序后依次学习，不区分"这是第一次学"还是"这是复习"。用户希望能分别控制"今天学几个新词"和"今天复习几个旧词"，并且需要在数据层面正式记录每个词被学习过的次数（新词 = 次数为 0）。

## 数据模型变更

### `word_progress` 表

新增列：

```sql
ALTER TABLE word_progress ADD COLUMN IF NOT EXISTS review_count INTEGER NOT NULL DEFAULT 0;
UPDATE word_progress SET review_count = 1 WHERE review_count = 0;
```

- 新增列默认值为 0，紧接着的 `UPDATE` 把所有已存在的旧记录（`review_count = 0`，即刚加列时的默认值）一次性回填为 1 —— 因为这些记录本来就代表"已经复习过至少一次"的词。
- 之后，应用代码永远不会把 `review_count` 写回 0（首次学习时写入 1），所以这条 `UPDATE` 是一次性、幂等安全的（不会误伤未来真正的新词，因为新词根本不会在 `word_progress` 里有行）。
- "新词"的判定方式不变：**在 `word_progress` 里没有对应行 = 新词**。`review_count` 字段本身不影响这个判定逻辑，只用于统计"今天学的是新词还是复习词"。

### `app_settings` 表

用两个新 key 替换 `daily_limit`：

```sql
INSERT INTO app_settings (key, value) VALUES ('new_words_limit', '10') ON CONFLICT (key) DO NOTHING;
INSERT INTO app_settings (key, value) VALUES ('review_words_limit', '20') ON CONFLICT (key) DO NOTHING;
```

旧的 `daily_limit` 行不需要删除（不再被读取，留着无害）。

## 后端逻辑（`app.py`）

### 今日进度统计（不需要额外的日志表）

因为 `review_count` 是累计值，可以复用它反推"今天这次学习是新词还是复习"：

- 今日新词数 = `word_progress` 中满足 `last_reviewed = today AND review_count = 1` 的行数
- 今日复习词数 = `word_progress` 中满足 `last_reviewed = today AND review_count > 1` 的行数

### `/api/next` 选词逻辑

1. 读取所有单词（`parse_words()`）和进度（`get_progress()`），像现在一样按 `jp` 分流：
   - `review_due`：有进度行、`next_review` 到期、且今天还没复习过的词，按 `level` 升序排序（与现在行为一致）
   - `new_words`：没有进度行的词，保持 `word.md` 中的原始顺序
2. 计算 `remaining_review = review_words_limit - today_review_count`，`remaining_new = new_words_limit - today_new_count`
3. 选词优先级（复习优先于新词）：
   - 若 `remaining_review > 0` 且 `review_due` 非空 → 取 `review_due[0]`
   - 否则若 `remaining_new > 0` 且 `new_words` 非空 → 取 `new_words[0]`
   - 否则 → 返回 `done: true`
     - 若两个 remaining 都 `<= 0` → `reason: "daily_limit"`
     - 否则（说明还有额度但对应池子已空）→ `reason: "all_done"`
4. 响应中把 `today_count`/`daily_limit` 替换为 `today_new_count`、`new_words_limit`、`today_review_count`、`review_words_limit`。

### `/api/review`

- 保存进度时读取当前 `review_count`（无记录则视为 0），写入 `review_count + 1`
- 其余等级升降逻辑不变

### `/api/settings`

- GET 返回 `{new_words_limit, review_words_limit}`
- POST 接受并保存这两个值（分别 `max(0, int(...))` 校验，允许设为 0 以临时关闭某一类学习）

## 前端变更（`templates/index.html`）

- 设置弹窗：把单个「每天背单词数量」输入框换成两个：「每天学习新词数量」「每天复习旧词数量」
- 顶部统计栏：从 `今日 X/Y` 改为类似 `新词 3/10 · 复习 8/20` 的双进度展示
- 卡片本身不显示单词的学过次数（用户明确表示不需要，保持卡片简洁）
- "done" 提示语区分两种情况：`daily_limit`（今日额度用完）与 `all_done`（没有更多到期词，但额度还没用完）

## 明确不做的事（Out of scope）

- 不在卡片上加"新词/复习"标签
- 不显示单词个体的学过次数
- 不改动等级/间隔算法本身（`scheduler.py` 不变）
- 不引入单独的"今日学习日志"表，复用 `review_count` + `last_reviewed` 推算今日统计

## 迁移与部署注意事项

- `schema.sql` 需要更新为包含上述 `ALTER TABLE` / `UPDATE` / 两条新 `INSERT`
- 已经部署过的用户需要在 Supabase SQL Editor 里手动执行这几条新增的 SQL（`schema.sql` 里注明"新增部分"，方便老用户增量执行）
- README 的部署教程和 UI 使用说明需要同步更新（"每日上限"改为"新词/复习词分别设置"）
