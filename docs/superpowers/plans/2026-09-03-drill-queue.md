# 本轮练习队列（drill）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当天点了「模糊」/「不认识」的词随机重现，答对才放走；练习过程完全不影响熟练度和 SRS 排期。

**Architecture:** 纯逻辑（建项 / 计数更新 / 选牌 / 存取）抽到 `static/drill.js`，不碰 DOM 不碰网络；`templates/index.html` 只负责调用它并渲染。`drill.js` 用 UMD-lite 尾巴（有 `module.exports` 就导出，没有就挂全局），浏览器当普通 `<script>` 加载，Node 里 `require` 同一份文件跑测试——零依赖、无构建步骤。后端一行不改。

**Tech Stack:** 原生 JS（无框架、无打包器）、Node 内置 `assert`（脚本式断言，对齐 `tests/test_srs_flow.py` 的风格）、GitHub Actions。

**设计文档：** `docs/superpowers/specs/2026-09-03-drill-queue-design.md`

---

## File Structure

| 文件 | 职责 | 状态 |
|---|---|---|
| `static/drill.js` | drill 纯逻辑：建项、答题后更新、选牌、localStorage 存取。不碰 DOM/网络 | 新建 |
| `tests/test_drill.js` | `drill.js` 的单元 + 场景测试，含反向断言 | 新建 |
| `templates/index.html` | 接线：加载 drill.js、改造 `loadNext()` / `score()`、练习卡渲染 | 修改 |
| `.github/workflows/tests.yml` | 增加 node job 跑 `tests/test_drill.js` | 修改 |

**为什么单独开文件而不是继续堆在 `index.html` 里**：`index.html` 的 `<script>` 已经 260 行，drill 逻辑再塞进去会越过能一次性读完的边界；更重要的是内联脚本没法在 Node 里 require，塞进去就等于放弃自动化测试。

**约定：分数编码** —— `1` = 不认识，`2` = 模糊，`3` = 认识（与 `app.py:218-223` 一致）。

---

### Task 1: `drill.js` 骨架 + `createDrillItem`

**Files:**
- Create: `static/drill.js`
- Test: `tests/test_drill.js`

- [ ] **Step 1: 写失败的测试**

创建 `tests/test_drill.js`：

```js
"use strict";
/**
 * static/drill.js 的测试。零依赖，直接跑：
 *
 *     node tests/test_drill.js
 *
 * 风格对齐 tests/test_srs_flow.py：断言里写清失败意味着什么，
 * 并且带反向断言（见最后一节）——测试必须能在代码变坏时红，
 * 否则它测的是自己而不是代码（DEVLOG v2.2 的教训）。
 */
const assert = require("assert");
const path = require("path");

const DRILL_JS = path.join(__dirname, "..", "static", "drill.js");
const Drill = require(DRILL_JS);

// 定长随机源：把 rng 换成可预测的值，断言才写得死。
const ALWAYS_MIN = () => 0;      // randInt 取下界
const ALWAYS_MAX = () => 0.999;  // randInt 取上界

const WORD = { jp: "間抜け", kana: "まぬけ", zh: "傻瓜", section: "名词", level: 2 };

function testCreateDrillItem() {
  // 认识 → 不进队列
  assert.strictEqual(Drill.createDrillItem(WORD, 3, ALWAYS_MIN), null,
    "点「认识」不应该产生练习项——它应该直接通过，本轮不再出现");

  // 模糊 → remaining 1，间隔 4~6
  const fuzzy = Drill.createDrillItem(WORD, 2, ALWAYS_MIN);
  assert.strictEqual(fuzzy.kind, "fuzzy");
  assert.strictEqual(fuzzy.remaining, 1, "「模糊」答对 1 次就该放走");
  assert.strictEqual(fuzzy.missStreak, 0);
  assert.strictEqual(fuzzy.countdown, 4, "「模糊」的重现间隔下界应为 4 张");
  assert.strictEqual(Drill.createDrillItem(WORD, 2, ALWAYS_MAX).countdown, 6,
    "「模糊」的重现间隔上界应为 6 张");

  // 不认识 → remaining 2，间隔 2~3（比模糊密）
  const unknown = Drill.createDrillItem(WORD, 1, ALWAYS_MIN);
  assert.strictEqual(unknown.kind, "unknown");
  assert.strictEqual(unknown.remaining, 2, "「不认识」要答对 2 次才放走");
  assert.strictEqual(unknown.countdown, 2, "「不认识」的重现间隔下界应为 2 张");
  assert.strictEqual(Drill.createDrillItem(WORD, 1, ALWAYS_MAX).countdown, 3,
    "「不认识」的重现间隔上界应为 3 张");

  // 词条快照要原样带上，练习卡完全靠它渲染（后端今天不会再发这个词）
  assert.deepStrictEqual(unknown.word, WORD,
    "练习项必须存词条快照，否则重新出牌时没有内容可显示");

  console.log("PASS  createDrillItem");
}

function main() {
  testCreateDrillItem();
  console.log("\n全部通过");
}

main();
```

- [ ] **Step 2: 跑测试确认它失败**

Run: `node tests/test_drill.js`
Expected: FAIL — `Error: Cannot find module '.../static/drill.js'`

- [ ] **Step 3: 写最小实现**

创建 `static/drill.js`：

```js
"use strict";
/**
 * 本轮练习队列（drill）的纯逻辑。不碰 DOM、不碰网络、不碰额度。
 * 设计文档：docs/superpowers/specs/2026-09-03-drill-queue-design.md
 *
 * 浏览器里当普通 <script> 加载，函数挂到 window.Drill；
 * Node 里 require 得到同一组函数，供 tests/test_drill.js 使用。
 * 用这个 UMD-lite 尾巴是为了不引入打包器——项目至今零构建步骤。
 */
(function (root) {
  // 首次点「不认识」要答对 2 次才放走，且重现得密（隔 2~3 张）；
  // 「模糊」答对 1 次即可，重现得疏（隔 4~6 张）。
  var DRILL_KINDS = {
    fuzzy: { remaining: 1, minGap: 4, maxGap: 6 },
    unknown: { remaining: 2, minGap: 2, maxGap: 3 },
  };

  function randInt(min, max, rng) {
    return min + Math.floor((rng || Math.random)() * (max - min + 1));
  }

  // score: 1=不认识 2=模糊 3=认识。「认识」不进队列，返回 null。
  function createDrillItem(word, score, rng) {
    var kind = score === 1 ? "unknown" : score === 2 ? "fuzzy" : null;
    if (!kind) return null;
    var cfg = DRILL_KINDS[kind];
    return {
      word: word,
      kind: kind,
      remaining: cfg.remaining,
      missStreak: 0,
      countdown: randInt(cfg.minGap, cfg.maxGap, rng),
    };
  }

  var api = {
    DRILL_KINDS: DRILL_KINDS,
    randInt: randInt,
    createDrillItem: createDrillItem,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Drill = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node tests/test_drill.js`
Expected: `PASS  createDrillItem` 然后 `全部通过`

- [ ] **Step 5: 提交**

```bash
git add static/drill.js tests/test_drill.js
git commit -m "Add drill.js with createDrillItem and its test harness"
```

---

### Task 2: `applyDrillAnswer` —— 答题后更新计数与放走判定

**Files:**
- Modify: `static/drill.js`（在 `createDrillItem` 之后新增）
- Test: `tests/test_drill.js`（新增 `testApplyDrillAnswer`）

- [ ] **Step 1: 写失败的测试**

在 `tests/test_drill.js` 的 `function main()` **之前**插入：

```js
function testApplyDrillAnswer() {
  const fuzzy = Drill.createDrillItem(WORD, 2, ALWAYS_MIN);   // remaining 1
  const unknown = Drill.createDrillItem(WORD, 1, ALWAYS_MIN); // remaining 2

  // 认识 → remaining 减 1；减到 0 就放走（返回 null）
  assert.strictEqual(Drill.applyDrillAnswer(fuzzy, 3, ALWAYS_MIN), null,
    "「模糊」的词答对 1 次就该被放走");

  const afterOne = Drill.applyDrillAnswer(unknown, 3, ALWAYS_MIN);
  assert.strictEqual(afterOne.remaining, 1, "「不认识」答对 1 次后还剩 1 次");
  assert.strictEqual(Drill.applyDrillAnswer(afterOne, 3, ALWAYS_MIN), null,
    "「不认识」答对第 2 次才放走");

  // 模糊/不认识 → remaining 纹丝不动（这是有意的，不是遗漏）
  const missed = Drill.applyDrillAnswer(unknown, 2, ALWAYS_MIN);
  assert.strictEqual(missed.remaining, 2,
    "练习中点「模糊」不能改变 remaining——只有「认识」才减");
  assert.strictEqual(Drill.applyDrillAnswer(unknown, 1, ALWAYS_MIN).remaining, 2,
    "练习中点「不认识」同样不能改变 remaining");

  // 逃生口：连续 3 次没答对就强制放走
  let item = unknown;
  item = Drill.applyDrillAnswer(item, 2, ALWAYS_MIN);
  assert.strictEqual(item.missStreak, 1);
  item = Drill.applyDrillAnswer(item, 1, ALWAYS_MIN);
  assert.strictEqual(item.missStreak, 2, "连败 2 次还不该放走");
  assert.strictEqual(Drill.applyDrillAnswer(item, 2, ALWAYS_MIN), null,
    "连续 3 次没答对必须强制放走，否则始终记不住的词会无限循环、done 永远不来");

  // 答对一次把连败清零
  let streaked = Drill.applyDrillAnswer(unknown, 2, ALWAYS_MIN);
  streaked = Drill.applyDrillAnswer(streaked, 2, ALWAYS_MIN);
  assert.strictEqual(streaked.missStreak, 2);
  const reset = Drill.applyDrillAnswer(streaked, 3, ALWAYS_MIN);
  assert.strictEqual(reset.missStreak, 0, "点一次「认识」必须把连败计数清零");
  assert.strictEqual(reset.remaining, 1);

  // 没被放走的项要重新排队，间隔仍按初始档位算（不随 remaining 变）
  assert.strictEqual(missed.countdown, 2,
    "「不认识」重排间隔应始终用 unknown 档位的下界 2，而不是切到 fuzzy 的 4");
  assert.strictEqual(Drill.applyDrillAnswer(unknown, 2, ALWAYS_MAX).countdown, 3);

  // 不能就地改原对象——调用方靠返回值决定去留
  assert.strictEqual(unknown.missStreak, 0,
    "applyDrillAnswer 必须返回新对象，不能修改传入的 item");

  console.log("PASS  applyDrillAnswer");
}
```

并把 `main()` 改成：

```js
function main() {
  testCreateDrillItem();
  testApplyDrillAnswer();
  console.log("\n全部通过");
}
```

- [ ] **Step 2: 跑测试确认它失败**

Run: `node tests/test_drill.js`
Expected: FAIL — `TypeError: Drill.applyDrillAnswer is not a function`

- [ ] **Step 3: 写最小实现**

在 `static/drill.js` 的 `createDrillItem` 之后、`var api = {` 之前插入：

```js
  // 连续这么多次没答对就强制放走。没有这个口子，一个始终记不住的词
  // 会在本轮无限循环，done 永远不来。
  var MISS_STREAK_LIMIT = 3;

  // 返回新的 item；返回 null 表示这个词被放走了，调用方应把它从队列删掉。
  // 只有「认识」减 remaining —— 模糊/不认识不改变它，这是需求明确要的。
  function applyDrillAnswer(item, score, rng) {
    var next = {
      word: item.word,
      kind: item.kind,
      remaining: item.remaining,
      missStreak: item.missStreak,
      countdown: item.countdown,
    };
    if (score === 3) {
      next.remaining -= 1;
      next.missStreak = 0;
    } else {
      next.missStreak += 1;
    }
    if (next.remaining <= 0 || next.missStreak >= MISS_STREAK_LIMIT) return null;
    var cfg = DRILL_KINDS[next.kind];
    next.countdown = randInt(cfg.minGap, cfg.maxGap, rng);
    return next;
  }
```

并把 `api` 对象改成：

```js
  var api = {
    DRILL_KINDS: DRILL_KINDS,
    MISS_STREAK_LIMIT: MISS_STREAK_LIMIT,
    randInt: randInt,
    createDrillItem: createDrillItem,
    applyDrillAnswer: applyDrillAnswer,
  };
```

- [ ] **Step 4: 跑测试确认通过**

Run: `node tests/test_drill.js`
Expected: `PASS  createDrillItem` / `PASS  applyDrillAnswer` / `全部通过`

- [ ] **Step 5: 提交**

```bash
git add static/drill.js tests/test_drill.js
git commit -m "Add applyDrillAnswer: only 认识 decrements, 3 misses force-release"
```

---

### Task 3: `tickAndPick` + `pickSoonest` —— 选牌

> **执行后修订**：Task 3 的质量审查提了两条，已在 `927f9a3` 落实，本节下面的原始代码块
> 保留为当时的规格记录，**实际代码与之有两处差异**：
> 1. `pickSoonest` 更名为 **`pickLongestWaiting`** —— 它取的是 countdown 最小、也就是
>    等最久/逾期最深的那个，而 "soonest" 读起来像「最快要到期的」，正好相反。
> 2. 抽出内部辅助 `cloneItem(it)`（不导出），`applyDrillAnswer` 和 `tickAndPick` 不再各自
>    手抄同样 5 个字段 —— 以后加字段漏改一处就是静默丢数据。
>
> 后续 Task 4、Task 8 已按新名字更新，见各自章节。

**Files:**
- Modify: `static/drill.js`
- Test: `tests/test_drill.js`（新增 `testPicking`）

- [ ] **Step 1: 写失败的测试**

在 `main()` 之前插入：

```js
function testPicking() {
  // 每出一张牌所有项 countdown 减 1；没到期就返回 null，让调用方去问后端
  const items = {
    a: { word: WORD, kind: "unknown", remaining: 2, missStreak: 0, countdown: 2 },
    b: { word: WORD, kind: "fuzzy", remaining: 1, missStreak: 0, countdown: 5 },
  };
  const t1 = Drill.tickAndPick(items, ALWAYS_MIN);
  assert.strictEqual(t1.pickedJp, null, "都没到期时不该出练习卡");
  assert.strictEqual(t1.items.a.countdown, 1);
  assert.strictEqual(t1.items.b.countdown, 4);
  assert.strictEqual(items.a.countdown, 2,
    "tickAndPick 必须返回新对象，不能修改传入的 items");

  // countdown 减到 0 就到期
  const t2 = Drill.tickAndPick(t1.items, ALWAYS_MIN);
  assert.strictEqual(t2.pickedJp, "a", "countdown 归零的项应该被选中出牌");
  assert.strictEqual(t2.items.a.countdown, 0);

  // 多个同时到期 → 按 rng 随机挑，不是永远挑第一个
  const both = {
    a: { word: WORD, kind: "unknown", remaining: 1, missStreak: 0, countdown: 1 },
    b: { word: WORD, kind: "fuzzy", remaining: 1, missStreak: 0, countdown: 1 },
  };
  assert.strictEqual(Drill.tickAndPick(both, ALWAYS_MIN).pickedJp, "a");
  assert.strictEqual(Drill.tickAndPick(both, ALWAYS_MAX).pickedJp, "b",
    "多个练习项同时到期时必须随机挑，否则永远只练排在前面的那个");

  // 空队列
  const empty = Drill.tickAndPick({}, ALWAYS_MIN);
  assert.strictEqual(empty.pickedJp, null);
  assert.deepStrictEqual(empty.items, {});

  // pickSoonest：额度用完时的兜底，等最久的（countdown 最小，可能是负数）先出
  assert.strictEqual(Drill.pickSoonest({}), null, "空队列没有兜底可出");
  assert.strictEqual(Drill.pickSoonest({
    a: { countdown: 3 },
    b: { countdown: -2 },
    c: { countdown: 1 },
  }), "b", "兜底应该出等得最久的那个（countdown 最小）");

  console.log("PASS  tickAndPick / pickSoonest");
}
```

`main()` 加一行 `testPicking();`（放在 `testApplyDrillAnswer();` 之后）。

- [ ] **Step 2: 跑测试确认它失败**

Run: `node tests/test_drill.js`
Expected: FAIL — `TypeError: Drill.tickAndPick is not a function`

- [ ] **Step 3: 写最小实现**

在 `static/drill.js` 的 `applyDrillAnswer` 之后插入：

```js
  // 每出一张牌调一次：所有项 countdown 减 1，然后从到期的里随机挑一个。
  // 返回 { items, pickedJp }；pickedJp 为 null 表示这一轮该去问后端要词。
  function tickAndPick(items, rng) {
    var next = {};
    var due = [];
    Object.keys(items).forEach(function (jp) {
      var it = items[jp];
      next[jp] = {
        word: it.word,
        kind: it.kind,
        remaining: it.remaining,
        missStreak: it.missStreak,
        countdown: it.countdown - 1,
      };
      if (next[jp].countdown <= 0) due.push(jp);
    });
    if (!due.length) return { items: next, pickedJp: null };
    var idx = Math.floor((rng || Math.random)() * due.length);
    return { items: next, pickedJp: due[idx] };
  }

  // 额度用完、后端说 done，但队列还有词时的兜底：等最久的（countdown 最小）先出。
  // 没有这一步，点过「模糊」的词会在额度耗尽的瞬间凭空消失。
  function pickSoonest(items) {
    var keys = Object.keys(items);
    if (!keys.length) return null;
    return keys.reduce(function (a, b) {
      return items[a].countdown <= items[b].countdown ? a : b;
    });
  }
```

`api` 里补上 `tickAndPick: tickAndPick,` 和 `pickSoonest: pickSoonest,`。

- [ ] **Step 4: 跑测试确认通过**

Run: `node tests/test_drill.js`
Expected: 三行 PASS + `全部通过`

- [ ] **Step 5: 提交**

```bash
git add static/drill.js tests/test_drill.js
git commit -m "Add tickAndPick and pickSoonest for drill card selection"
```

---

### Task 4: localStorage 存取与跨天失效

**Files:**
- Modify: `static/drill.js`
- Test: `tests/test_drill.js`（新增 `testStorage`）

- [ ] **Step 1: 写失败的测试**

在 `main()` 之前插入：

```js
// 假 localStorage：Node 里没有，测试自己造一个。
function fakeStorage(initial) {
  const data = Object.assign({}, initial);
  return {
    data: data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = v; },
  };
}

// 会抛异常的 storage：模拟隐私模式 / 配额满
function throwingStorage() {
  return {
    getItem: () => { throw new Error("SecurityError"); },
    setItem: () => { throw new Error("QuotaExceededError"); },
  };
}

function testStorage() {
  const TODAY = "2026-09-03";
  const item = Drill.createDrillItem(WORD, 1, ALWAYS_MIN);

  // 存 → 取，原样回来
  const s = fakeStorage();
  Drill.saveDrill("jp", TODAY, { "間抜け": item }, s);
  assert.deepStrictEqual(Drill.loadDrill("jp", TODAY, s), { "間抜け": item });

  // 按 book 分开存，互不干扰（和现有的 tango_extended_<book> 一个路数）
  assert.deepStrictEqual(Drill.loadDrill("en", TODAY, s), {},
    "日语的练习队列不能被英语本读到");
  assert.ok("tango_drill_jp" in s.data, "localStorage 键名应为 tango_drill_<book>");

  // 跨天自动失效
  assert.deepStrictEqual(Drill.loadDrill("jp", "2026-09-04", s), {},
    "「本轮」= 今天，跨天必须清空练习队列");

  // 没存过 / 存了垃圾 → 空队列，不抛
  assert.deepStrictEqual(Drill.loadDrill("jp", TODAY, fakeStorage()), {});
  assert.deepStrictEqual(
    Drill.loadDrill("jp", TODAY, fakeStorage({ "tango_drill_jp": "不是 JSON" })), {},
    "存储里是坏数据时应当降级为空队列，而不是让整个页面抛异常");

  // storage 本身抛异常（隐私模式）→ 降级为纯内存，不能白屏
  assert.deepStrictEqual(Drill.loadDrill("jp", TODAY, throwingStorage()), {});
  assert.doesNotThrow(
    () => Drill.saveDrill("jp", TODAY, { "間抜け": item }, throwingStorage()),
    "localStorage 写失败时必须静默降级，不能让打分流程中断");

  console.log("PASS  loadDrill / saveDrill");
}
```

`main()` 加一行 `testStorage();`。

- [ ] **Step 2: 跑测试确认它失败**

Run: `node tests/test_drill.js`
Expected: FAIL — `TypeError: Drill.saveDrill is not a function`

- [ ] **Step 3: 写最小实现**

在 `static/drill.js` 的 `pickLongestWaiting`（Task 3 中由 `pickSoonest` 更名而来）之后插入：

```js
  function drillKey(book) {
    return "tango_drill_" + book;
  }

  // 跨天自动失效：存的 date 不是今天就整个丢弃（「本轮」= 今天）。
  // localStorage 在隐私模式 / 配额满时会抛，抛了就当空队列——
  // 宁可丢练习队列，也不能让打分流程中断、页面卡死。
  function loadDrill(book, today, storage) {
    try {
      var raw = storage.getItem(drillKey(book));
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.date !== today) return {};
      return parsed.items || {};
    } catch (e) {
      return {};
    }
  }

  function saveDrill(book, today, items, storage) {
    try {
      storage.setItem(drillKey(book), JSON.stringify({ date: today, items: items }));
    } catch (e) {
      // 降级为纯内存：刷新会丢练习队列，但不会白屏
    }
  }
```

`api` 里补上 `drillKey: drillKey,`、`loadDrill: loadDrill,`、`saveDrill: saveDrill,`。

- [ ] **Step 4: 跑测试确认通过**

Run: `node tests/test_drill.js`
Expected: 四行 PASS + `全部通过`

- [ ] **Step 5: 提交**

```bash
git add static/drill.js tests/test_drill.js
git commit -m "Add drill localStorage persistence with same-day scoping and safe fallback"
```

---

### Task 5: 场景回归测试 + 反向断言

把设计文档「行为验算」那张表变成可执行的断言，并证明这个测试有鉴别力。

**Files:**
- Modify: `tests/test_drill.js`

- [ ] **Step 1: 写失败的测试**

在 `main()` 之前插入（`const fs = require("fs");` 放到文件顶部的 require 区）：

```js
// 把一次完整的练习过程跑完，返回「练了几次」。
// scores 的第一个元素是首次点击（决定档位），其余是练习卡上的点击。
function runScenario(scores, DrillMod) {
  const M = DrillMod || Drill;
  let item = M.createDrillItem(WORD, scores[0], ALWAYS_MIN);
  if (!item) return { drills: 0, released: "immediate" };
  let drills = 0;
  for (let i = 1; i < scores.length; i++) {
    drills++;
    item = M.applyDrillAnswer(item, scores[i], ALWAYS_MIN);
    if (!item) return { drills: drills, released: "yes" };
  }
  return { drills: drills, released: "no" };
}

const 认识 = 3, 模糊 = 2, 不认识 = 1;

function testScenarios() {
  // 设计文档「行为验算」那张表，逐行断言
  assert.deepStrictEqual(runScenario([认识]),
    { drills: 0, released: "immediate" }, "认识 → 不进队列");
  assert.deepStrictEqual(runScenario([模糊, 认识]),
    { drills: 1, released: "yes" }, "模糊 → 认识：练 1 次自然放走");
  assert.deepStrictEqual(runScenario([模糊, 模糊, 模糊, 模糊]),
    { drills: 3, released: "yes" }, "模糊 → 连续 3 次没答对：逃生放走");
  assert.deepStrictEqual(runScenario([不认识, 认识, 认识]),
    { drills: 2, released: "yes" }, "不认识 → 答对 2 次自然放走");
  assert.deepStrictEqual(runScenario([不认识, 模糊, 模糊, 模糊]),
    { drills: 3, released: "yes" }, "不认识 → 连续 3 次没答对：逃生放走");
  assert.deepStrictEqual(runScenario([不认识, 认识, 模糊, 模糊, 模糊]),
    { drills: 4, released: "yes" },
    "不认识 → 认识清零连败后，需要重新连败 3 次才逃生（最长练 5 次的那条路径）");

  // 「不认识」必须比「模糊」难放走，否则 remaining=2 这档设计就白设了
  assert.strictEqual(runScenario([模糊, 认识]).released, "yes");
  assert.strictEqual(runScenario([不认识, 认识]).released, "no",
    "同样答对 1 次，「模糊」该放走而「不认识」不该——两档必须有区别");

  console.log("PASS  场景回归");
}

// 反向断言：把逃生阈值改掉，上面的逃生场景必须不再成立。
// 否则这个测试测的是它自己，而不是代码（DEVLOG v2.2 的教训）。
function testReverseAssertion() {
  const src = fs.readFileSync(DRILL_JS, "utf8");
  const NEEDLE = "var MISS_STREAK_LIMIT = 3;";
  assert.ok(src.includes(NEEDLE),
    "找不到逃生阈值的声明，反向断言已失效，请同步更新 NEEDLE");
  const mutated = src.replace(NEEDLE, "var MISS_STREAK_LIMIT = 99;");

  const fake = { exports: {} };
  new Function("module", "exports", mutated)(fake, fake.exports);
  const Broken = fake.exports;
  assert.strictEqual(Broken.MISS_STREAK_LIMIT, 99, "变异没生效");

  const r = runScenario([模糊, 模糊, 模糊, 模糊], Broken);
  assert.strictEqual(r.released, "no",
    "把逃生阈值提到 99 之后，连败 3 次竟然仍会放走——" +
    "说明放走是别的原因造成的，本测试对逃生口没有鉴别力，需要重新设计场景");

  console.log("PASS  反向断言（逃生阈值确实在起作用）");
}
```

`main()` 加两行：`testScenarios();` 和 `testReverseAssertion();`。

- [ ] **Step 2: 跑测试**

Run: `node tests/test_drill.js`
Expected: 六行 PASS + `全部通过`

本任务不需要改 `static/drill.js`——Task 1~4 的实现已经满足这些场景，这些断言是对着设计文档独立写的交叉验证。**如果有断言失败，说明前面某个任务的实现与设计不符，回到对应任务修实现，不要改断言去迁就实现。**

- [ ] **Step 3: 确认反向断言真的能红**

临时把 `static/drill.js` 里的 `var MISS_STREAK_LIMIT = 3;` 改成 `= 4;`，重跑。

Run: `node tests/test_drill.js`
Expected: FAIL —「模糊 → 连续 3 次没答对：逃生放走」那条断言失败。

改回 `3`，重跑确认恢复通过。这一步是验证测试本身有鉴别力，不提交中间状态。

- [ ] **Step 4: 提交**

```bash
git add tests/test_drill.js
git commit -m "Add drill scenario regression tests and reverse assertion"
```

---

### Task 6: CI 接入

**Files:**
- Modify: `.github/workflows/tests.yml`

- [ ] **Step 1: 加 node job**

把 `.github/workflows/tests.yml` 整个替换为：

```yaml
# 回归测试。纯标准库/内置模块，不装依赖，几秒跑完。
# 它挡的是 DEVLOG v2.4 那类 bug：每段代码单独看都对，但组合起来跑一个月才失效。
name: tests

on:
  push:
  pull_request:

jobs:
  srs-flow:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"    # 与 runtime.txt 保持一致
      - name: 斩词全流程 + 反向断言
        run: python tests/test_srs_flow.py

  drill-logic:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - name: 本轮练习队列 + 反向断言
        run: node tests/test_drill.js
```

- [ ] **Step 2: 本地确认两个测试都能跑**

Run: `python tests/test_srs_flow.py && node tests/test_drill.js`
Expected: 两个都打印 PASS，退出码 0

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/tests.yml
git commit -m "Run drill logic tests in CI"
```

---

### Task 7: 接线 —— 加载 drill.js，抽出熟练度条渲染

**Files:**
- Modify: `templates/index.html`

> 行号会随改动漂移，以函数名和相邻代码为准定位。

- [ ] **Step 1: 加载 drill.js**

在 katex 的 script 标签之后（当前 `:295`，`auto-render.min.js` 那行下面）加一行：

```html
  <script src="{{ url_for('static', filename='drill.js') }}"></script>
```

- [ ] **Step 2: 新增 drill 状态与存取包装**

在状态声明区（当前 `:346-350`，`let currentBook = ...` 那行之后）加：

```js
    // 本轮练习队列：当天点了「模糊」/「不认识」的词随机重现，答对才放走。
    // 纯逻辑在 static/drill.js，这里只管状态和渲染。
    let drill = {};
    let isDrillCard = false;

    function reloadDrill() {
      drill = Drill.loadDrill(currentBook, todayStr(), localStorage);
    }

    function persistDrill() {
      Drill.saveDrill(currentBook, todayStr(), drill, localStorage);
    }
```

- [ ] **Step 3: 切换单词本时换成对应的队列**

在 `switchBook()`（当前 `:359`）里，`updateBookSwitch();` 那行**之前**加一行：

```js
      reloadDrill();
```

- [ ] **Step 4: 抽出熟练度条渲染**

`loadNext()` 里这段（当前 `:482-489`）：

```js
      const bar = document.getElementById("level-bar");
      bar.innerHTML = "";
      for (let i = 0; i < 5; i++) {
        const d = document.createElement("div");
        d.className = "dot" + (i < data.level ? " filled" : "");
        bar.appendChild(d);
      }
```

替换为一次调用：

```js
      renderLevelBar(data.level);
```

并在 `flip()` 函数（当前 `:494`）**之前**新增：

```js
    function renderLevelBar(level) {
      const bar = document.getElementById("level-bar");
      bar.innerHTML = "";
      for (let i = 0; i < 5; i++) {
        const d = document.createElement("div");
        d.className = "dot" + (i < level ? " filled" : "");
        bar.appendChild(d);
      }
    }
```

- [ ] **Step 5: 手工验证没改坏现有行为**

启动：`python app.py`（需要 `SUPABASE_URL` / `SUPABASE_KEY` 环境变量），打开 `http://localhost:5001`。

Expected：出词、翻牌、熟练度条、切换单词本全部与改动前一致。浏览器 Console 无报错，输入 `window.Drill` 应看到函数对象。

- [ ] **Step 6: 提交**

```bash
git add templates/index.html
git commit -m "Load drill.js, add drill state, extract renderLevelBar"
```

---

### Task 8: 改造 `loadNext()` —— 出练习卡

**Files:**
- Modify: `templates/index.html`（`loadNext()`，当前 `:448`）

- [ ] **Step 1: 新增练习卡渲染函数**

在 `loadNext()` **之前**新增：

```js
    // 练习卡完全靠 drill 里的快照渲染——后端今天不会再发这个词。
    // 和普通卡的区别只有两处：section 位置显示进度、不更新 stats（练习不计入额度）。
    function showDrillCard(jp) {
      const item = drill[jp];
      isDrillCard = true;
      current = item.word;
      showWordFace();
      renderText(document.getElementById("jp"), item.word.jp);
      renderText(document.getElementById("kana"), item.word.kana || "");
      document.getElementById("kana").style.display =
        currentBook === "en" ? "none" : "block";
      renderText(document.getElementById("answer"), item.word.zh);
      document.getElementById("section-tag").textContent =
        `练习中 · 还需答对 ${item.remaining} 次`;
      renderLevelBar(item.word.level);
    }
```

- [ ] **Step 2: 改造 `loadNext()`**

把整个 `loadNext()` 替换为：

```js
    async function loadNext() {
      updateExitButton();

      // 卡片外观先复位，两条出牌路径（练习卡 / 后端卡）都要用；
      // 提到网络请求之前也顺带避免了加载期间残留上一张的按钮状态。
      document.getElementById("score-btns").style.display = "none";
      document.getElementById("answer").style.display = "none";
      document.getElementById("flip-btn").style.display = "block";
      document.getElementById("done-actions").style.display = "none";

      // 每出一张牌，练习队列整体前进一格；有到期的就优先出练习卡
      const ticked = Drill.tickAndPick(drill, Math.random);
      drill = ticked.items;
      persistDrill();
      if (ticked.pickedJp) {
        showDrillCard(ticked.pickedJp);
        return;
      }

      const extended = isExtendedToday();
      const params = new URLSearchParams({ book: currentBook });
      if (extended) params.set("extended", "1");
      const res = await fetch("/api/next?" + params.toString());
      const data = await res.json();

      if (data.done) {
        // 额度用完时不能直接 done，否则点过「模糊」的词会凭空消失：
        // 用户既没答对它、当天也再见不到它。先把练习队列放完。
        const fallback = Drill.pickLongestWaiting(drill);
        if (fallback) {
          showDrillCard(fallback);
          return;
        }

        const progressLine = `新词 ${data.today_new_count}/${data.new_words_limit} · 复习 ${data.today_review_count}/${data.review_words_limit}`;
        const head = data.reason === "daily_limit"
          ? "今天的额度已用完！"
          : "所有到期单词复习完了！";

        showDoneMessage(`${head}<br><span class="sub">${progressLine}</span>`);
        document.getElementById("flip-btn").style.display = "none";
        document.getElementById("stats").textContent = "";
        document.getElementById("done-actions").style.display = "flex";
        return;
      }

      isDrillCard = false;
      showWordFace();
      current = data;
      renderText(document.getElementById("jp"), data.jp);
      renderText(document.getElementById("kana"), data.kana || "");
      document.getElementById("kana").style.display = currentBook === "en" ? "none" : "block";
      renderText(document.getElementById("answer"), data.zh);
      document.getElementById("section-tag").textContent = data.section;
      renderLevelBar(data.level);

      document.getElementById("stats").textContent =
        `新词 ${data.today_new_count}/${data.new_words_limit} · 复习 ${data.today_review_count}/${data.review_words_limit}`;
    }
```

- [ ] **Step 3: 初始化时载入队列**

在文件末尾清理旧 key 那行（当前 `:601`，`localStorage.removeItem("tango_extended_date");`）**之后**、首次调用 `loadNext()` **之前**加：

```js
    reloadDrill();
```

- [ ] **Step 4: 手工验证出牌路径**

刷新页面。Expected：出词、翻牌、打分都正常（此时 `score()` 还没接，练习卡不会自然产生）。Console 无报错。

在 Console 里手工塞一个练习项：

```js
drill = { "测试词": { word: {jp:"测试词",kana:"テスト",zh:"test",section:"名词",level:2},
  kind:"fuzzy", remaining:1, missStreak:0, countdown:1 } };
loadNext();
```

Expected：立刻出现「测试词」，section 位置显示「练习中 · 还需答对 1 次」，熟练度条 2 格。

- [ ] **Step 5: 提交**

```bash
git add templates/index.html
git commit -m "Serve drill cards from loadNext, including the done fallback"
```

---

### Task 9: 改造 `score()` —— 建项、更新、冻结熟练度

**Files:**
- Modify: `templates/index.html`（`score()`，当前 `:501`）

- [ ] **Step 1: 替换 `score()`**

把整个 `score()` 替换为：

```js
    async function score(s) {
      if (isFreeReview) {
        freeReviewIndex++;
        showFreeReviewCard();
        return;
      }

      // 练习卡：不调任何接口。熟练度只由首次点击决定，这里一概不动。
      if (isDrillCard) {
        const jp = current.jp;
        const next = Drill.applyDrillAnswer(drill[jp], s, Math.random);
        if (next) drill[jp] = next;
        else delete drill[jp];   // remaining 归零或连败 3 次 —— 放走
        persistDrill();
        loadNext();
        return;
      }

      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jp: current.jp, score: s, book: currentBook }),
      });
      const data = await res.json();

      if (data.reached_max_level) {
        const wantsMastery = confirm(`「${current.jp}」已经记得很牢固了，要斩掉吗？`);
        if (wantsMastery) {
          await fetch("/api/mastery", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jp: current.jp, book: currentBook }),
          });
        }
      }

      // 首次点「模糊」/「不认识」才进练习队列。level 必须用 /api/review 返回的
      // 新等级，不能用 current.level（那是打分前的旧值）——否则点了「不认识」的词
      // 在练习卡上会显示比实际高一级。
      // reached_max_level 只在 s === 3 时为真，斩词和建练习项不会同时发生。
      const item = Drill.createDrillItem({
        jp: current.jp,
        kana: current.kana,
        zh: current.zh,
        section: current.section,
        level: data.level,
      }, s, Math.random);
      if (item) {
        drill[current.jp] = item;
        persistDrill();
      }

      loadNext();
    }
```

- [ ] **Step 2: 手工验证核心路径**

打开浏览器 Network 面板，刷新页面。

1. 对一个词点「不认识」→ 应看到一次 `POST /api/review`；记下这个词。
2. 继续答 2~3 张卡 → 这个词应重新出现，section 位置写「练习中 · 还需答对 2 次」，熟练度条比打分前少 1 格。
3. 在练习卡上点任意分数 → **Network 面板不应出现任何新请求**。
4. 在练习卡上点两次「认识」（中间会隔几张）→ 第二次之后该词不再出现。
5. 页面顶部 `新词 x/y · 复习 m/n` 在整个练习过程中不变。

- [ ] **Step 3: 提交**

```bash
git add templates/index.html
git commit -m "Wire drill queue into score(): first click owns SRS, drills are free"
```

---

### Task 10: 完整手工验收

**Files:** 无改动，仅验证。逐条勾，任一条不符回到对应任务修。

- [ ] 首次点「认识」：熟练度 +1，不进练习队列，本轮不再出现
- [ ] 首次点「模糊」：熟练度不变，隔 4~6 张重现；重现时点「认识」→ 放走
- [ ] 首次点「不认识」：熟练度 −1，隔 2~3 张重现；需答对 2 次才放走
- [ ] 练习卡上点任何分数都不发 `/api/review`（Network 面板确认）
- [ ] 熟练度条显示打分**后**的等级：level 3 的词点「不认识」，练习卡上显示 2 格
- [ ] 练习卡正面不直接给答案，点「显示答案」才翻——和普通卡一致
- [ ] 连续 3 次点模糊/不认识 → 放走；中间点一次「认识」→ 连败清零，需重新连败 3 次
- [ ] 额度用完时若练习队列非空，先放完练习卡才显示「今天的额度已用完！」
- [ ] 斩词弹窗只在首次点击时可能触发，练习卡上不重复弹
- [ ] 切到另一本再切回来，练习队列还在；两本的队列互不干扰
- [ ] 刷新页面练习队列还在（DevTools → Application → Local Storage 里能看到 `tango_drill_jp`）
- [ ] 自由复习模式下不产生练习卡，也不影响已有队列
- [ ] 「继续学习」模式下练习卡照常工作

- [ ] **确认工作区干净**

```bash
git status --short   # 应为空
```

---

## 回滚

全部改动集中在 `static/drill.js`（新文件）、`tests/test_drill.js`（新文件）、
`templates/index.html`、`.github/workflows/tests.yml`。后端与数据库零改动、无迁移，
`git revert` 即可完全回退，不会留下脏数据。
