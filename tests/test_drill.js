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

function main() {
  testCreateDrillItem();
  testApplyDrillAnswer();
  console.log("\n全部通过");
}

main();
