import os
from datetime import date

from flask import Flask, jsonify, render_template, request
from supabase import create_client

from parser import WORD_FILES, parse_words
from scheduler import next_review, is_due

app = Flask(__name__)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


DEFAULT_LIMITS = {"new_words_limit": 10, "review_words_limit": 20}


def resolve_book(value):
    return value if value in WORD_FILES else "jp"


def get_limit(key, book):
    """每个单词本的额度独立存储，键名形如 new_words_limit_jp。

    分书之前只有一个全局键（new_words_limit），那时只有日语本，
    因此日语本在找不到分书键时回落到旧键，保留用户原有设置。
    """
    scoped_key = f"{key}_{book}"
    res = sb.table("app_settings").select("key,value").in_("key", [scoped_key, key]).execute()
    values = {row["key"]: row["value"] for row in res.data}
    if scoped_key in values:
        return int(values[scoped_key])
    if book == "jp" and key in values:
        return int(values[key])
    return DEFAULT_LIMITS[key]


def get_new_words_limit(book):
    return get_limit("new_words_limit", book)


def get_review_words_limit(book):
    return get_limit("review_words_limit", book)


PAGE_SIZE = 1000


def fetch_all(make_query):
    """分页取全量。

    PostgREST 单次响应有行数上限（Supabase 默认 1000），直接 select 会被静默
    截断——被截掉的词会重新变成“没学过的新词”。这里翻页到空页为止，并按实际
    返回条数推进游标，所以不依赖上限具体是多少。
    """
    rows = []
    start = 0
    while True:
        page = make_query().range(start, start + PAGE_SIZE - 1).execute().data
        rows.extend(page)
        if not page:
            return rows
        start += len(page)


def get_progress(book):
    rows = fetch_all(lambda: sb.table("word_progress").select(
        "jp,level,next_review,last_reviewed,review_count,mastered"
    ).eq("book", book))
    return {row["jp"]: row for row in rows}


def get_today_new_count(book):
    today = date.today().isoformat()
    return len(fetch_all(lambda: sb.table("word_progress").select("jp").eq(
        "book", book).eq("last_reviewed", today).eq("review_count", 1)))


def get_today_review_count(book):
    today = date.today().isoformat()
    return len(fetch_all(lambda: sb.table("word_progress").select("jp").eq(
        "book", book).eq("last_reviewed", today).gt("review_count", 1)))


def save_progress(jp, level, next_review_date, review_count, book):
    today = date.today().isoformat()
    # 冲突目标必须写全 (jp, book)。主键只有 jp 的话，同一条文本在两个单词本之间
    # 会互相覆盖——upsert 把已有行的 book 直接改掉，等于把进度从一本搬到另一本。
    sb.table("word_progress").upsert({
        "jp": jp,
        "book": book,
        "level": level,
        "next_review": next_review_date,
        "last_reviewed": today,
        "review_count": review_count,
    }, on_conflict="jp,book").execute()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        book = resolve_book(request.args.get("book"))
        return jsonify({
            "book": book,
            "new_words_limit": get_new_words_limit(book),
            "review_words_limit": get_review_words_limit(book),
        })
    data = request.get_json()
    book = resolve_book(data.get("book"))
    new_words_limit = max(0, int(data["new_words_limit"]))
    review_words_limit = max(0, int(data["review_words_limit"]))
    sb.table("app_settings").upsert(
        {"key": f"new_words_limit_{book}", "value": str(new_words_limit)}).execute()
    sb.table("app_settings").upsert(
        {"key": f"review_words_limit_{book}", "value": str(review_words_limit)}).execute()
    return jsonify({
        "ok": True,
        "book": book,
        "new_words_limit": new_words_limit,
        "review_words_limit": review_words_limit,
    })


@app.route("/api/next")
def get_next():
    book = resolve_book(request.args.get("book"))
    words = parse_words(book)
    progress = get_progress(book)
    new_words_limit = get_new_words_limit(book)
    review_words_limit = get_review_words_limit(book)
    today_new_count = get_today_new_count(book)
    today_review_count = get_today_review_count(book)
    today = date.today().isoformat()
    extended = request.args.get("extended") == "1"

    review_due = []
    new_words = []
    for w in words:
        p = progress.get(w["jp"])
        if p is None:
            new_words.append({**w, "level": 0})
        elif p.get("mastered"):
            continue
        elif (p["last_reviewed"] is None or p["last_reviewed"] < today) and is_due(p["next_review"]):
            review_due.append({**w, "level": p["level"], "next_review": p["next_review"]})

    # 逾期最久的先出，同一天到期的再按熟悉度从低到高。
    # 此前只按 level 升序：复习需求（一个词升到满级要 4 次复习，10 新词/天 ≈ 40 次/天）
    # 长期高于复习额度（默认 20），缺口就全部落在队尾——也就是熟悉度最高的那批词身上。
    # 它们永远排不到、也就永远升不到 level 5，斩词的触发条件因此一次都没被满足过。
    review_due.sort(key=lambda x: (x["next_review"], x["level"]))

    new_words_by_section = {}
    for w in new_words:
        new_words_by_section.setdefault(w["section"], []).append(w)
    if new_words_by_section:
        sections = list(new_words_by_section.values())
        cursor = today_new_count % len(sections)
        new_words = [sections[cursor][0]]
    else:
        new_words = []

    remaining_review = review_words_limit - today_review_count
    remaining_new = new_words_limit - today_new_count

    def build_response(word):
        return jsonify({
            "done": False,
            "jp": word["jp"],
            "kana": word["kana"],
            "zh": word["zh"],
            "section": word["section"],
            "level": word["level"],
            "today_new_count": today_new_count,
            "new_words_limit": new_words_limit,
            "today_review_count": today_review_count,
            "review_words_limit": review_words_limit,
        })

    if (extended or remaining_review > 0) and review_due:
        return build_response(review_due[0])
    # 新词只受新词额度约束，不因为复习有积压而停发。
    #
    # v2.4 曾在这里加过 `and not review_due`（还有到期词没复习完就一个新词都不发），
    # 作为积压的自动刹车。它确实拦住了积压，但代价是把用户设的新词额度悄悄归零，
    # 画面上还只说"额度已用完"——正是本项目反复吃亏的那种静默失败。
    #
    # 现在把这个权衡交还给用户，规则是「复习额度 >= 4 x 新词额度」：一个词升到满级
    # 要 4 次复习，所以 N 新词/天在稳态下产生约 4N 次/天的复习需求。这还是每次都
    # 答对的理想值，「模糊」「不会」都会让它更高，保守按 5 倍设。
    #
    # 比例不对时积压会增长，但不再是 v2.4 那种死锁：复习队列已改为按到期日排序，
    # 缺口均摊到所有到期词，不会再出现高熟悉度的词被永久饿死、level 5 结构性不可达。
    # 积压条数由下面的 review_backlog 返回并显示在完成画面上，不再是隐形的。
    if (extended or remaining_new > 0) and new_words:
        return build_response(new_words[0])

    # 只有"还有词可出、但被额度挡住"才算额度用完。此前用 or 串联三个条件，
    # 新词额度已满、复习额度尚有剩余时会误报成"所有到期单词复习完了"。
    blocked_review = bool(review_due) and not extended and remaining_review <= 0
    blocked_new = bool(new_words) and not extended and remaining_new <= 0
    reason = "daily_limit" if blocked_review or blocked_new else "all_done"
    return jsonify({
        "done": True,
        "reason": reason,
        # 到期但今天还没复习的词数。积压不再挡住新词，但它会让复习越拖越晚，
        # 所以必须能被看见——否则用户唯一能观察到的现象就是"进度莫名其妙变慢"。
        "review_backlog": len(review_due),
        "today_new_count": today_new_count,
        "new_words_limit": new_words_limit,
        "today_review_count": today_review_count,
        "review_words_limit": review_words_limit,
    })


@app.route("/api/review", methods=["POST"])
def review():
    data = request.get_json()
    jp = data["jp"]
    score = int(data["score"])
    book = resolve_book(data.get("book"))

    progress = get_progress(book)
    current = progress.get(jp, {})
    current_level = current.get("level", 0)
    current_count = current.get("review_count", 0)

    if score == 1:
        new_level = max(0, current_level - 1)
    elif score == 2:
        new_level = current_level
    else:
        new_level = min(5, current_level + 1)

    new_count = current_count + 1
    save_progress(jp, new_level, next_review(new_level), new_count, book)

    return jsonify({"ok": True, "level": new_level, "reached_max_level": new_level == 5})


@app.route("/api/mastery", methods=["POST"])
def mastery():
    data = request.get_json()
    jp = data["jp"]
    book = resolve_book(data.get("book"))
    sb.table("word_progress").update({"mastered": True}).eq("jp", jp).eq("book", book).execute()
    return jsonify({"ok": True})


@app.route("/api/review_today")
def review_today():
    book = resolve_book(request.args.get("book"))
    today = date.today().isoformat()
    studied_jp = {row["jp"] for row in fetch_all(
        lambda: sb.table("word_progress").select("jp").eq("book", book).eq(
            "last_reviewed", today))}
    words = parse_words(book)
    today_words = [w for w in words if w["jp"] in studied_jp]
    return jsonify(today_words)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
