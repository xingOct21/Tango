"""SRS 长周期回归测试：斩词能不能真的被触发。

为什么需要它：斩词的每一段代码单独看都是对的，失效来自「队列排序 + 每日额度 +
持续灌新词」三者叠加 25 天以上的累积效应（详见 DEVLOG v2.4）。这种 bug 只有把
时间跑起来才会暴露，所以这里用假时钟 + 内存假 Supabase 客户端，把两个月压缩成几秒。

v2.6 起还多守一条：新词供给只受新词额度约束（「有积压就不发新词」的闸门已删除），
所以「复习额度 >= 4 x 新词额度」变成用户要自己遵守的约束。下面用两组配置分别验证
比例正确时不积压、比例失衡时确实会积压——把这个代价钉成可执行的事实。

覆盖范围：`/api/next` 与 `/api/review` 的业务逻辑随时间的演化。
**不覆盖**真实数据库的约束（主键冲突、ON CONFLICT 42P10 那类），那些只能在
Supabase 上验证 —— 假客户端只是 PostgREST 的近似。

只用标准库，不需要装 flask / supabase：

    python tests/test_srs_flow.py
"""
import datetime
import os
import sys
import tempfile
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(REPO, "app.py")
sys.path.insert(0, REPO)

# 可持续配置：复习额度 >= 4 x 新词额度。一个词升到满级要 4 次复习，
# 所以 N 新词/天在稳态下产生约 4N 次/天的复习需求。
NEW_LIMIT = 5
REVIEW_LIMIT = 40

# 比例失衡的配置（v2.4 之前的线上设置）：10 新词/天意味着约 40 次/天的复习需求，
# 压在 20 的产能上。v2.6 删掉「有积压就不发新词」的闸门后，这个比例的后果由用户
# 自己承担，所以下面用它跑两件事：验证积压确实会堆起来，以及做排序的反向断言。
STRAINED_NEW = 10
STRAINED_REVIEW = 20

DAYS = 58
START = datetime.date(2026, 1, 1)

CLOCK = {"today": START}
STORE = {"word_progress": [], "app_settings": []}
PK = {"word_progress": ("jp", "book"), "app_settings": ("key",)}


# --------------------------------------------------------------- 假 Supabase
class Query:
    def __init__(self, table):
        self.table = table
        self.filters = []
        self.rng = None
        self.pending = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r, c=col, v=val: r.get(c) == v)
        return self

    def gt(self, col, val):
        self.filters.append(lambda r, c=col, v=val: (r.get(c) or 0) > v)
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r, c=col, v=set(vals): r.get(c) in v)
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def upsert(self, row, on_conflict=None):
        keys = tuple(on_conflict.split(",")) if on_conflict else PK[self.table]
        self.pending = ("upsert", row, keys)
        return self

    def update(self, patch):
        self.pending = ("update", patch, None)
        return self

    def _matching(self):
        return [r for r in STORE[self.table] if all(f(r) for f in self.filters)]

    def execute(self):
        if self.pending is None:
            rows = self._matching()
            if self.rng:
                a, b = self.rng
                rows = rows[a:b + 1]
            return types.SimpleNamespace(data=[dict(r) for r in rows])
        op, payload, keys = self.pending
        if op == "upsert":
            for r in STORE[self.table]:
                if all(r.get(k) == payload.get(k) for k in keys):
                    r.update(payload)
                    return types.SimpleNamespace(data=[dict(r)])
            row = {"mastered": False, "review_count": 0, "level": 0, "last_reviewed": None}
            row.update(payload)
            STORE[self.table].append(row)
            return types.SimpleNamespace(data=[dict(row)])
        for r in self._matching():
            r.update(payload)
        return types.SimpleNamespace(data=[])


class FakeClient:
    def table(self, name):
        return Query(name)


# ------------------------------------------------- 假 flask（只桩掉胶水层）
class FakeRequest:
    def __init__(self):
        self.args = {}
        self.json_body = None

    def get_json(self):
        return self.json_body


FAKE_REQUEST = FakeRequest()


class FakeFlask:
    def __init__(self, *_a, **_k):
        pass

    def route(self, *_a, **_k):
        return lambda f: f

    def run(self, *_a, **_k):
        pass


def install_stubs():
    supabase = types.ModuleType("supabase")
    supabase.create_client = lambda url, key: FakeClient()
    sys.modules["supabase"] = supabase

    flask = types.ModuleType("flask")
    flask.Flask = FakeFlask
    flask.jsonify = lambda *a, **k: (a[0] if a else k)   # 直接返回 payload
    flask.render_template = lambda *a, **k: ""
    flask.request = FAKE_REQUEST
    sys.modules["flask"] = flask

    os.environ.setdefault("SUPABASE_URL", "http://fake")
    os.environ.setdefault("SUPABASE_KEY", "fake")


class FakeDate:
    @staticmethod
    def today():
        return CLOCK["today"]


class FakeDateTime:
    @staticmethod
    def now():
        return datetime.datetime.combine(CLOCK["today"], datetime.time())


# ---------------------------------------------------------------- 合成词表
def write_word_file(path, count=600, sections=3):
    """不读真实 word.md：词表内容变了不应该让这个测试红/绿。"""
    lines = ["# 测试词表", ""]
    per = count // sections
    for s in range(sections):
        lines += [f"## 分类{s}", "", "|日语|假名|中文|", "|---|---|---|"]
        for i in range(per):
            n = s * per + i
            lines.append(f"|word{n:04d}|kana{n:04d}|释义{n:04d}|")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------- 被测模块
def load_app(source):
    """把 app.py 的源码 exec 成一个独立模块，便于对同一份逻辑做变异测试。"""
    mod = types.ModuleType("app_under_test")
    mod.__file__ = APP_PY
    exec(compile(source, APP_PY, "exec"), mod.__dict__)
    mod.date = FakeDate          # app.py 里是 from datetime import date
    return mod


SORT_NEW = 'review_due.sort(key=lambda x: (x["next_review"], x["level"]))'
SORT_OLD = 'review_due.sort(key=lambda x: x["level"])'


def pre_fix_source(source):
    """把复习队列的排序还原成 v2.4 之前的 level 升序，用于反向断言。

    v2.4 的另一处改动（新词分支的 `and not review_due` 闸门）已在 v2.6 删除，
    所以这里只剩排序这一处可还原 —— 而它本来就是死锁的主因：缺口 100% 落在
    队尾（熟悉度最高的那批），它们永远排不到，level 5 结构性不可达。

    替换必须真的发生 —— 否则这个测试会在代码被重写后静默失效，
    变成 v2.2 那种「恒真、不具备证伪能力」的验证。
    """
    mutated = source.replace(SORT_NEW, SORT_OLD)
    assert SORT_OLD in mutated and SORT_NEW not in mutated, \
        "找不到复习队列的排序语句，反向断言已失效，请同步更新 SORT_NEW/SORT_OLD"
    return mutated


# ------------------------------------------------------------------ 模拟器
def simulate(mod, days=DAYS, new_limit=NEW_LIMIT, review_limit=REVIEW_LIMIT):
    """每次都答「记住了」、满级弹窗一律选「斩」—— 最理想的用户。"""
    STORE["word_progress"].clear()
    STORE["app_settings"].clear()
    STORE["app_settings"] += [
        {"key": "new_words_limit_jp", "value": str(new_limit)},
        {"key": "review_words_limit_jp", "value": str(review_limit)},
    ]

    result = {"max_level": 0, "prompts": 0, "first_prompt_day": None}
    for d in range(days):
        CLOCK["today"] = START + datetime.timedelta(days=d)
        for _ in range(5000):
            FAKE_REQUEST.args = {"book": "jp"}
            FAKE_REQUEST.json_body = None
            nxt = mod.get_next()
            if nxt["done"]:
                break
            FAKE_REQUEST.args = {}
            FAKE_REQUEST.json_body = {"jp": nxt["jp"], "score": 3, "book": "jp"}
            rv = mod.review()
            result["max_level"] = max(result["max_level"], rv["level"])
            if rv["reached_max_level"]:
                result["prompts"] += 1
                if result["first_prompt_day"] is None:
                    result["first_prompt_day"] = d
                FAKE_REQUEST.json_body = {"jp": nxt["jp"], "book": "jp"}
                mod.mastery()

    today = CLOCK["today"].isoformat()
    result["backlog"] = sum(
        1 for r in STORE["word_progress"]
        if not r.get("mastered")
        and (r["last_reviewed"] is None or r["last_reviewed"] < today)
        and r["next_review"] <= today)
    return result


# ------------------------------------------------------------------- 断言
def main():
    install_stubs()
    tmp = tempfile.mkdtemp(prefix="tango-test-")
    word_file = os.path.join(tmp, "word.md")
    write_word_file(word_file)

    import parser as word_parser
    import scheduler
    word_parser.WORD_FILES["jp"] = word_file
    scheduler.datetime = FakeDateTime

    with open(APP_PY, encoding="utf-8") as f:
        source = f.read()

    # 1) 比例正确时（复习 >= 4 x 新词）：满级必须真的能达到，斩词弹窗必须真的会弹
    fixed = simulate(load_app(source))
    assert fixed["max_level"] == 5, (
        f"没有任何词升到 level 5（最高 {fixed['max_level']}）—— 斩词永远不会触发。"
        " 多半是 /api/next 的复习队列又把高熟悉度的词排到了队尾，见 DEVLOG v2.4")
    assert fixed["prompts"] > 0, "达到了 level 5 但 reached_max_level 没有为真"
    assert fixed["first_prompt_day"] <= 35, (
        f"首次斩词弹窗拖到第 {fixed['first_prompt_day']} 天；理论最短 25 天"
        "（升满级四次复习的间隔 1+3+7+14），超过 35 天说明队列又开始饿死高等级的词")

    # 2) 比例正确时积压不该系统性堆积：末日未复习的到期词不超过一天的复习额度
    assert fixed["backlog"] <= REVIEW_LIMIT, (
        f"{DAYS} 天后仍积压 {fixed['backlog']} 个到期未复习的词，超过单日复习额度"
        f" {REVIEW_LIMIT}。复习 {REVIEW_LIMIT} / 新词 {NEW_LIMIT} 满足 4 倍规则，"
        " 这个配置下不该有积压——多半是选词或排序逻辑退化了")

    # 3) 比例失衡时积压必须真的堆起来。v2.6 删掉了「有积压就不发新词」的闸门，
    #    4 倍规则从此是用户要自己遵守的约束，而不是代码强制的。这条断言把这个
    #    代价钉成可执行的事实：不满足 4 倍，积压就会涨，而且没有东西会拦住它。
    strained = simulate(load_app(source), new_limit=STRAINED_NEW,
                        review_limit=STRAINED_REVIEW)
    assert strained["backlog"] > STRAINED_REVIEW * 2, (
        f"复习 {STRAINED_REVIEW} / 新词 {STRAINED_NEW}（需求约 {STRAINED_NEW * 4}/天）"
        f" 跑 {DAYS} 天，积压只有 {strained['backlog']}，远低于预期。"
        " 要么 4 倍规则的前提变了，要么又有什么东西在偷偷限制新词供给——"
        " 后者正是 v2.6 删掉的那道闸门，别让它以别的形式回来")

    # 4) 反向断言：把排序还原成 v2.4 之前的 level 升序，第 1 条必须失败。
    #    否则这个测试测的是它自己，而不是代码（DEVLOG v2.2 的教训）。
    #    必须用失衡配置——比例正确时没有缺口，level 升序也不会饿死任何词。
    broken = simulate(load_app(pre_fix_source(source)), new_limit=STRAINED_NEW,
                      review_limit=STRAINED_REVIEW)
    assert broken["prompts"] == 0 and broken["max_level"] < 5, (
        f"还原成修复前的排序后，斩词竟然仍能触发"
        f"（最高 level {broken['max_level']}，弹窗 {broken['prompts']} 次）。"
        " 这说明本测试已经失去鉴别力，需要重新设计场景")

    print(f"PASS  复习 {REVIEW_LIMIT}/新词 {NEW_LIMIT}：最高 level {fixed['max_level']}，"
          f"第 {fixed['first_prompt_day']} 天首次斩词，"
          f"弹窗 {fixed['prompts']} 次，末日积压 {fixed['backlog']}")
    print(f"      复习 {STRAINED_REVIEW}/新词 {STRAINED_NEW}（比例失衡）："
          f"末日积压 {strained['backlog']}，符合预期——4 倍规则由用户负责")
    print(f"      反向验证：还原成 level 升序排序后最高只到 level {broken['max_level']}，"
          f"弹窗 {broken['prompts']} 次")


if __name__ == "__main__":
    main()
