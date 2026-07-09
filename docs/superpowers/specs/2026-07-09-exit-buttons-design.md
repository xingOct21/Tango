# 继续学习 / 自由复习 —— 手动退出按钮

## 背景

完成当日额度后，用户可以点击"继续学习"（解除当日新词/复习数量限额，`localStorage.tango_extended_date`）或"复习"（自由复习今天学过的内容，`isFreeReview`，不写入 SRS 状态）。

这两个模式进入后界面和平时学习一样（翻卡 + 打分），且都没有手动退出入口：

- "继续学习"只有跨天（日期变化）才会自动失效，同一天内无法退出。
- "自由复习"只有把当天列表放完才会自然结束，中途无法退出。

## 需求

- **自由复习**：保留现有的自然结束条件（列表放完），新增手动退出按钮。
- **继续学习**：不加自然结束条件（维持现状），新增手动"返回"按钮。

## 设计

在页面左上角新增一个固定定位（`position: fixed`）的按钮 `#exit-mode-btn`，样式低调（参考 `#settings-btn`），默认隐藏。文字和行为随当前状态切换，两种模式互斥展示（同一时刻最多一种生效）：

| 当前状态 | 按钮文字 | 点击行为 |
|---|---|---|
| `isFreeReview === true` | `← 退出复习` | `isFreeReview = false`；清空 `freeReviewList`/`freeReviewIndex`；调用 `loadNext()` |
| `isFreeReview === false` 且今天已解除限额（`localStorage.tango_extended_date === today`） | `← 返回` | `localStorage.removeItem("tango_extended_date")`；调用 `loadNext()` |
| 两者都不是 | （隐藏） | — |

判断优先级：先检查 `isFreeReview`，再检查 extended 状态——因为自由复习是从完成态临时进入的一次性回放，退出复习后如果 extended 仍然有效，按钮应变为"返回"而不是直接消失。

### 涉及的改动点

1. **HTML**：新增 `<button id="exit-mode-btn">`，固定在左上角，独立于 `#header` 的居中布局。
2. **CSS**：`#exit-mode-btn` 新增样式（`position: fixed; top/left`，颜色/字号参考 `#settings-btn`），默认 `display: none`。
3. **JS**：
   - 新增 `updateExitButton()` 函数，按上表逻辑设置按钮文字与 `display`，在以下时机调用：`loadNext()` 开始处、`startFreeReview()`、`showFreeReviewCard()` 中回退到 done 状态时、`continueLearning()` 之后。
   - 新增 `exitCurrentMode()` 函数（按钮的 `onclick`），根据当前状态执行上表对应行为。

### 不涉及的改动

- 不修改 `/api/next`、`/api/review_today` 等后端逻辑。
- 不改变自由复习"不写入 SRS 状态"的行为。
- 不给"继续学习"加自然结束边界。

## 测试关注点

- 正常流程（未触发继续学习/复习）：按钮不显示。
- 点击"继续学习"进入后：按钮显示"返回"；点击后限额恢复（下次 `/api/next` 不带 `extended=1`），按钮隐藏。
- 点击"复习"进入自由复习：按钮显示"退出复习"；中途点击后退出，`loadNext()` 正常触发（若额度仍满则显示完成态，若 extended 仍有效则继续显示"返回"按钮）。
- 自由复习自然放完列表：按钮从"退出复习"切换为完成态下的 `done-actions`（此时若 extended 仍生效，需确认"返回"按钮与 `done-actions` 不冲突同时显示）。
