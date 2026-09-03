"use strict";
/**
 * static/drill.js 的测试。零依赖，直接跑：
 *
 *     node tests/test_drill.js
 *
 * 风格对齐 tests/test_srs_flow.py：断言里写清失败意味着什么，
 * 反向断言随后续任务补上（测试必须能在代码变坏时红，否则它测的是
 * 自己而不是代码 —— DEVLOG v2.2 的教训）。
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
  assert.strictEqual(item.missStreak, 1, "第一次没答对，连败计数应该从 0 变成 1");
  item = Drill.applyDrillAnswer(item, 1, ALWAYS_MIN);
  assert.strictEqual(item.missStreak, 2, "连败 2 次还不该放走");
  assert.strictEqual(Drill.applyDrillAnswer(item, 2, ALWAYS_MIN), null,
    "连续 3 次没答对必须强制放走，否则始终记不住的词会无限循环、done 永远不来");

  // 答对一次把连败清零
  let streaked = Drill.applyDrillAnswer(unknown, 2, ALWAYS_MIN);
  streaked = Drill.applyDrillAnswer(streaked, 2, ALWAYS_MIN);
  assert.strictEqual(streaked.missStreak, 2, "连续两次没答对，连败计数应该累计到 2");
  const reset = Drill.applyDrillAnswer(streaked, 3, ALWAYS_MIN);
  assert.strictEqual(reset.missStreak, 0, "点一次「认识」必须把连败计数清零");
  assert.strictEqual(reset.remaining, 1, "「认识」在清零连败的同时也要把 remaining 减 1");

  // 没被放走的项要重新排队，间隔仍按初始档位算（不随 remaining 变）
  assert.strictEqual(missed.countdown, 2,
    "「不认识」重排间隔应始终用 unknown 档位的下界 2，而不是切到 fuzzy 的 4");
  assert.strictEqual(Drill.applyDrillAnswer(unknown, 2, ALWAYS_MAX).countdown, 3,
    "「不认识」重排间隔的上界应为 3 张");

  // 不能就地改原对象——调用方靠返回值决定去留
  assert.strictEqual(unknown.missStreak, 0,
    "applyDrillAnswer 必须返回新对象，不能修改传入的 item");

  console.log("PASS  applyDrillAnswer");
}

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

  // pickLongestWaiting：额度用完时的兜底，等最久的（countdown 最小，可能是负数）先出
  assert.strictEqual(Drill.pickLongestWaiting({}), null, "空队列没有兜底可出");
  assert.strictEqual(Drill.pickLongestWaiting({
    a: { countdown: 3 },
    b: { countdown: -2 },
    c: { countdown: 1 },
  }), "b", "兜底应该出等得最久的那个（countdown 最小）");

  console.log("PASS  tickAndPick / pickLongestWaiting");
}

// 假 localStorage：Node 里没有，测试自己造一个。
// 注意：真的 localStorage 会把 value 强制转成字符串，这个假的不会。
// 目前无所谓 —— saveDrill 传进去的永远是 JSON.stringify 的结果，本来就是字符串。
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

  // 形状不对的练习项必须在入口丢掉
  const dirty = fakeStorage({
    "tango_drill_jp": JSON.stringify({ date: TODAY, items: {
      good: item,
      noCountdown: { word: WORD, kind: "fuzzy", remaining: 1, missStreak: 0 },
      nanCountdown: { word: WORD, kind: "fuzzy", remaining: 1, missStreak: 0, countdown: null },
      noWord: { kind: "fuzzy", remaining: 1, missStreak: 0, countdown: 3 },
      badKind: { word: WORD, kind: "typo", remaining: 1, missStreak: 0, countdown: 3 },
      spent: { word: WORD, kind: "fuzzy", remaining: 0, missStreak: 0, countdown: 3 },
    } }),
  });
  assert.deepStrictEqual(Object.keys(Drill.loadDrill("jp", TODAY, dirty)), ["good"],
    "形状不对的练习项必须在 loadDrill 入口丢掉：countdown 不是数字的话，"
    + "NaN <= 0 恒为 false，这个词永远排不到队，却又可能被 pickLongestWaiting 选中，"
    + "渲染 item.word.jp 时崩掉");

  console.log("PASS  loadDrill / saveDrill");
}

function main() {
  testCreateDrillItem();
  testApplyDrillAnswer();
  testPicking();
  testStorage();
  console.log("\n全部通过");
}

main();
