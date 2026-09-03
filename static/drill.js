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
