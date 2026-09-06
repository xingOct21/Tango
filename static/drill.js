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

  // DrillItem 的浅拷贝。applyDrillAnswer 和 tickAndPick 都要「改一份新的、
  // 不动传入的那份」，字段列表写两遍的话，以后加字段漏改一处就是静默丢数据。
  function cloneItem(it) {
    return {
      word: it.word,
      kind: it.kind,
      remaining: it.remaining,
      missStreak: it.missStreak,
      countdown: it.countdown,
    };
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

  // 连续这么多次没答对就强制放走。没有这个口子，一个始终记不住的词
  // 会在本轮无限循环，done 永远不来。
  var MISS_STREAK_LIMIT = 3;

  // 返回新的 item；返回 null 表示这个词被放走了，调用方应把它从队列删掉。
  // 只有「认识」减 remaining —— 模糊/不认识不改变它，这是需求明确要的。
  function applyDrillAnswer(item, score, rng) {
    var next = cloneItem(item);
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

  // 每出一张牌调一次：所有项 countdown 减 1，然后从到期的里随机挑一个。
  // 返回 { items, pickedJp }；pickedJp 为 null 表示这一轮该去问后端要词。
  function tickAndPick(items, rng) {
    var next = {};
    var due = [];
    Object.keys(items).forEach(function (jp) {
      var it = items[jp];
      next[jp] = cloneItem(it);
      next[jp].countdown -= 1;
      if (next[jp].countdown <= 0) due.push(jp);
    });
    if (!due.length) return { items: next, pickedJp: null };
    var idx = Math.floor((rng || Math.random)() * due.length);
    return { items: next, pickedJp: due[idx] };
  }

  // 额度用完、后端说 done，但队列还有词时的兜底：等最久的（countdown 最小）先出。
  // 没有这一步，点过「模糊」的词会在额度耗尽的瞬间凭空消失。
  function pickLongestWaiting(items) {
    var keys = Object.keys(items);
    if (!keys.length) return null;
    return keys.reduce(function (a, b) {
      return items[a].countdown <= items[b].countdown ? a : b;
    });
  }

  function drillKey(book) {
    return "tango_drill_" + book;
  }

  // localStorage 里的东西可能被手改、被旧版本写坏，或者 JSON 往返把 NaN 变成 null。
  // 形状不对的项必须在入口就丢掉：countdown 一旦不是数字，`countdown <= 0` 恒为
  // false，这个词永远排不进到期队列；而 pickLongestWaiting 的比较在这种值下又可能
  // 把它选中，接着渲染 item.word.jp 就崩。宁可丢一条练习记录，也不能让整轮学习卡死。
  function isValidItem(it) {
    return !!it
      && !!it.word && typeof it.word.jp === "string"
      && Object.prototype.hasOwnProperty.call(DRILL_KINDS, it.kind)
      && typeof it.remaining === "number" && it.remaining > 0
      && typeof it.missStreak === "number" && it.missStreak >= 0
      && typeof it.countdown === "number" && isFinite(it.countdown);
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
      var items = parsed.items || {};
      var clean = {};
      Object.keys(items).forEach(function (jp) {
        if (isValidItem(items[jp])) {
          clean[jp] = items[jp];
        } else {
          // 静默丢弃正是这个项目栽过跟头的地方（见 DEVLOG：v2.0 的两个按钮
          // 交付起就没工作过，藏了三个月）。用户看不到这条，devtools 里能看到。
          console.warn("[drill] 丢弃形状不对的练习项：", book, jp, items[jp]);
        }
      });
      return clean;
    } catch (e) {
      console.warn("[drill] 读取练习队列失败，本轮降级为空队列：", e.message);
      return {};
    }
  }

  function saveDrill(book, today, items, storage) {
    try {
      storage.setItem(drillKey(book), JSON.stringify({ date: today, items: items }));
    } catch (e) {
      // 降级为纯内存：刷新会丢练习队列，但不会白屏
      console.warn("[drill] 保存练习队列失败，降级为纯内存：", e.message);
    }
  }

  var api = {
    DRILL_KINDS: DRILL_KINDS,
    MISS_STREAK_LIMIT: MISS_STREAK_LIMIT,
    randInt: randInt,
    createDrillItem: createDrillItem,
    applyDrillAnswer: applyDrillAnswer,
    tickAndPick: tickAndPick,
    pickLongestWaiting: pickLongestWaiting,
    loadDrill: loadDrill,
    saveDrill: saveDrill,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Drill = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
