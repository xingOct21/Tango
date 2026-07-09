# 继续学习 / 自由复习 手动退出按钮 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在页面左上角加一个共享的固定退出按钮，让用户可以随时手动退出"继续学习"（解除限额模式）或"自由复习"模式，而不必等到跨天或复习列表放完。

**Architecture:** 单文件改动（`templates/index.html`，内联 CSS + JS）。新增一个 `#exit-mode-btn` 按钮，文字/可见性由新增的 `updateExitButton()` 函数根据 `isFreeReview` 和 `localStorage.tango_extended_date` 两个既有状态量决定；点击按钮触发 `exitCurrentMode()`，按当前状态清理对应的状态并调用既有的 `loadNext()`。不新增文件，不改动后端 `app.py`。

**Tech Stack:** 原生 HTML/CSS/JS（无构建、无测试框架），Flask 提供静态模板。

**Spec:** `docs/superpowers/specs/2026-07-09-exit-buttons-design.md`

---

## Task 1: 新增按钮标记、样式，及状态判断辅助函数

**Files:**
- Modify: `templates/index.html`（CSS 样式块、`<body>` 顶部、`<script>` 内 `loadNext()`/`continueLearning()`）

- [ ] **Step 1: 在 CSS 中新增 `#exit-mode-btn` 样式**

在 `#settings-btn:hover { background: #eee; color: #555; }` 之后（当前第 42 行附近）插入：

```css
    #exit-mode-btn {
      display: none;
      position: fixed;
      top: 16px;
      left: 16px;
      background: none;
      border: none;
      cursor: pointer;
      font-size: 0.85rem;
      color: #aaa;
      padding: 6px 10px;
      border-radius: 6px;
    }
    #exit-mode-btn:hover { background: #eee; color: #555; }
```

- [ ] **Step 2: 在 `<body>` 顶部新增按钮元素**

把：

```html
<body>
  <div id="header">
```

改成：

```html
<body>
  <button id="exit-mode-btn" onclick="exitCurrentMode()"></button>
  <div id="header">
```

- [ ] **Step 3: 新增 `todayStr()` / `isExtendedToday()` 辅助函数，并替换现有重复的日期计算**

在 `<script>` 开头（`let current = null;` 等变量声明之后，`async function loadNext() {` 之前）插入：

```js
    function todayStr() {
      return new Date().toISOString().slice(0, 10);
    }

    function isExtendedToday() {
      return localStorage.getItem("tango_extended_date") === todayStr();
    }
```

然后把 `loadNext()` 里的：

```js
    async function loadNext() {
      const today = new Date().toISOString().slice(0, 10);
      const extended = localStorage.getItem("tango_extended_date") === today;
      const res = await fetch("/api/next" + (extended ? "?extended=1" : ""));
```

改成：

```js
    async function loadNext() {
      const extended = isExtendedToday();
      const res = await fetch("/api/next" + (extended ? "?extended=1" : ""));
```

再把 `continueLearning()` 里的：

```js
    function continueLearning() {
      const today = new Date().toISOString().slice(0, 10);
      localStorage.setItem("tango_extended_date", today);
      loadNext();
    }
```

改成：

```js
    function continueLearning() {
      localStorage.setItem("tango_extended_date", todayStr());
      loadNext();
    }
```

- [ ] **Step 4: 确认没有语法错误**

Run: `python3 -c "import re; s = open('templates/index.html').read(); assert s.count('<script>') == 1 and s.count('</script>') == 1; print('ok')"`
Expected: `ok`（粗略检查文件仍然是一个 script 块、没有被截断）

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "Add exit-mode button markup/styles and date helper functions"
```

---

## Task 2: 实现 `updateExitButton()` / `exitCurrentMode()` 并接入四个调用点

**Files:**
- Modify: `templates/index.html`（`<script>` 内 `loadNext()`、`startFreeReview()`、`showFreeReviewCard()`、`continueLearning()`）

- [ ] **Step 1: 新增 `updateExitButton()` 和 `exitCurrentMode()` 函数**

在 Task 1 新增的 `isExtendedToday()` 函数之后插入：

```js
    function updateExitButton() {
      const btn = document.getElementById("exit-mode-btn");
      if (isFreeReview) {
        btn.textContent = "← 退出复习";
        btn.style.display = "block";
      } else if (isExtendedToday()) {
        btn.textContent = "← 返回";
        btn.style.display = "block";
      } else {
        btn.style.display = "none";
      }
    }

    function exitCurrentMode() {
      if (isFreeReview) {
        isFreeReview = false;
        freeReviewList = [];
        freeReviewIndex = 0;
      } else {
        localStorage.removeItem("tango_extended_date");
      }
      loadNext();
    }
```

- [ ] **Step 2: 在 `loadNext()` 开头调用 `updateExitButton()`**

把（Task 1 之后的版本）：

```js
    async function loadNext() {
      const extended = isExtendedToday();
      const res = await fetch("/api/next" + (extended ? "?extended=1" : ""));
```

改成：

```js
    async function loadNext() {
      updateExitButton();
      const extended = isExtendedToday();
      const res = await fetch("/api/next" + (extended ? "?extended=1" : ""));
```

- [ ] **Step 3: 在 `startFreeReview()` 里进入自由复习后调用 `updateExitButton()`**

把：

```js
    async function startFreeReview() {
      const res = await fetch("/api/review_today");
      freeReviewList = await res.json();
      freeReviewIndex = 0;
      isFreeReview = true;
      document.getElementById("done-actions").style.display = "none";
      showFreeReviewCard();
    }
```

改成：

```js
    async function startFreeReview() {
      const res = await fetch("/api/review_today");
      freeReviewList = await res.json();
      freeReviewIndex = 0;
      isFreeReview = true;
      updateExitButton();
      document.getElementById("done-actions").style.display = "none";
      showFreeReviewCard();
    }
```

- [ ] **Step 4: 在 `showFreeReviewCard()` 自由复习自然结束分支里调用 `updateExitButton()`**

把：

```js
      if (freeReviewIndex >= freeReviewList.length) {
        isFreeReview = false;
        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">复习完了！</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("done-actions").style.display = "flex";
        return;
      }
```

改成：

```js
      if (freeReviewIndex >= freeReviewList.length) {
        isFreeReview = false;
        updateExitButton();
        document.getElementById("card").innerHTML =
          `<div style="text-align:center;color:#555;font-size:1.1rem;line-height:2">复习完了！</div>`;
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("done-actions").style.display = "flex";
        return;
      }
```

- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "Wire updateExitButton/exitCurrentMode into learning and free-review flows"
```

---

## Task 3: 浏览器手动验证四个场景

这个项目没有前端测试框架（纯内联 JS，无构建流程），用浏览器实际走一遍 spec 里的"测试关注点"来验证。需要本地能跑 Flask（`SUPABASE_URL`/`SUPABASE_KEY` 环境变量已配置）。

**Files:** 无代码改动，仅验证。

- [ ] **Step 1: 启动本地服务**

Run: `python3 app.py`
Expected: 输出类似 `Running on http://0.0.0.0:5001`，进程保持运行（用 `run_in_background` 或另开终端）。

- [ ] **Step 2: 正常流程下按钮不显示**

用浏览器打开 `http://localhost:5001/`，观察左上角。
Expected: 没有任何"返回"/"退出复习"按钮（正常学习/复习中的额度未耗尽状态）。

- [ ] **Step 3: 验证"继续学习"的返回按钮**

先耗尽当日额度（或临时把设置里的新词/复习数量调到 0 方便测试），触发完成态，点击"继续学习"。
Expected: 左上角出现"← 返回"按钮；正常翻卡界面照常工作。

点击"← 返回"。
Expected: 按钮消失（因为限额已恢复且没有真正到期的词了，会回到完成态或正常队列，取决于当天数据）；之后 `/api/next` 请求不再带 `?extended=1`（可用浏览器 Network 面板确认请求 URL）。

- [ ] **Step 4: 验证"复习"的退出按钮**

回到完成态，点击"复习"。
Expected: 左上角出现"← 退出复习"按钮，卡片显示"自由复习 1/N"。

翻一张卡后（不用打分也行），点击"← 退出复习"。
Expected: 立即离开自由复习，回到 `loadNext()` 的正常渲染（完成态或下一张正常卡片，取决于当天额度状态）；如果此时"继续学习"仍处于解除限额状态，按钮应变为"← 返回"而不是消失。

- [ ] **Step 5: 验证自由复习自然放完时按钮与 done-actions 共存**

再次点击"复习"，把 `freeReviewList` 里的卡片全部翻完打分到底（不要中途退出）。
Expected: 显示"复习完了！"，同时"继续学习"/"复习"两个 `done-actions` 按钮出现；若此前"继续学习"仍生效，左上角"← 返回"按钮应和 `done-actions` 同时可见、不重叠遮挡（如有视觉重叠，记录下来但不在本计划范围内修复，回报给用户决定是否需要额外调整）。

- [ ] **Step 6: 停止本地服务**

Run: 结束 Step 1 启动的进程（如用了 `run_in_background`，用对应工具停止；否则 Ctrl+C）。
