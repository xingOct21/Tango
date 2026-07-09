import os
from datetime import date

from flask import Flask, jsonify, render_template, request
from supabase import create_client

from parser import parse_words
from scheduler import next_review, is_due

app = Flask(__name__)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def get_new_words_limit():
    res = sb.table("app_settings").select("value").eq("key", "new_words_limit").execute()
    return int(res.data[0]["value"]) if res.data else 10


def get_review_words_limit():
    res = sb.table("app_settings").select("value").eq("key", "review_words_limit").execute()
    return int(res.data[0]["value"]) if res.data else 20


def get_progress():
    res = sb.table("word_progress").select(
        "jp,level,next_review,last_reviewed,review_count,mastered"
    ).execute()
    return {row["jp"]: row for row in res.data}


def get_today_new_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).eq("review_count", 1).execute()
    return len(res.data)


def get_today_review_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).gt("review_count", 1).execute()
    return len(res.data)


def save_progress(jp, level, next_review_date, review_count):
    today = date.today().isoformat()
    sb.table("word_progress").upsert({
        "jp": jp,
        "level": level,
        "next_review": next_review_date,
        "last_reviewed": today,
        "review_count": review_count,
    }).execute()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify({
            "new_words_limit": get_new_words_limit(),
            "review_words_limit": get_review_words_limit(),
        })
    data = request.get_json()
    new_words_limit = max(0, int(data["new_words_limit"]))
    review_words_limit = max(0, int(data["review_words_limit"]))
    sb.table("app_settings").upsert({"key": "new_words_limit", "value": str(new_words_limit)}).execute()
    sb.table("app_settings").upsert({"key": "review_words_limit", "value": str(review_words_limit)}).execute()
    return jsonify({
        "ok": True,
        "new_words_limit": new_words_limit,
        "review_words_limit": review_words_limit,
    })


@app.route("/api/next")
def get_next():
    words = parse_words()
    progress = get_progress()
    daily_limit = get_daily_limit()
    today_count = get_today_count()
    today = date.today().isoformat()

    remaining = daily_limit - today_count
    if remaining <= 0:
        return jsonify({"done": True, "reason": "daily_limit",
                        "today_count": today_count, "daily_limit": daily_limit})

    due = []
    for w in words:
        p = progress.get(w["jp"])
        if p is None:
            due.append({**w, "level": 0})
        elif (p["last_reviewed"] is None or p["last_reviewed"] < today) and is_due(p["next_review"]):
            due.append({**w, "level": p["level"]})

    due.sort(key=lambda x: x["level"])

    if not due:
        return jsonify({"done": True, "reason": "all_done",
                        "today_count": today_count, "daily_limit": daily_limit})

    word = due[0]
    return jsonify({
        "done": False,
        "jp": word["jp"],
        "kana": word["kana"],
        "zh": word["zh"],
        "section": word["section"],
        "level": word["level"],
        "today_count": today_count,
        "daily_limit": daily_limit,
        "remaining": remaining,
    })


@app.route("/api/review", methods=["POST"])
def review():
    data = request.get_json()
    jp = data["jp"]
    score = int(data["score"])

    progress = get_progress()
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
    save_progress(jp, new_level, next_review(new_level), new_count)

    return jsonify({"ok": True, "level": new_level, "reached_max_level": new_level == 5})


@app.route("/api/mastery", methods=["POST"])
def mastery():
    data = request.get_json()
    jp = data["jp"]
    sb.table("word_progress").update({"mastered": True}).eq("jp", jp).execute()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
