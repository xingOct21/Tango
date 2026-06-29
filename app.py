import os
from datetime import date

from flask import Flask, jsonify, render_template, request
from supabase import create_client

from parser import parse_words
from scheduler import next_review, is_due

app = Flask(__name__)
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def get_daily_limit():
    res = sb.table("app_settings").select("value").eq("key", "daily_limit").execute()
    return int(res.data[0]["value"]) if res.data else 20


def get_progress():
    res = sb.table("word_progress").select("jp,level,next_review,last_reviewed").execute()
    return {row["jp"]: row for row in res.data}


def get_today_count():
    today = date.today().isoformat()
    res = sb.table("word_progress").select("jp").eq("last_reviewed", today).execute()
    return len(res.data)


def save_progress(jp, level, next_review_date):
    today = date.today().isoformat()
    sb.table("word_progress").upsert({
        "jp": jp,
        "level": level,
        "next_review": next_review_date,
        "last_reviewed": today,
    }).execute()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "GET":
        return jsonify({"daily_limit": get_daily_limit()})
    data = request.get_json()
    new_limit = max(1, int(data["daily_limit"]))
    sb.table("app_settings").upsert({"key": "daily_limit", "value": str(new_limit)}).execute()
    return jsonify({"ok": True, "daily_limit": new_limit})


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
    current_level = progress.get(jp, {}).get("level", 0)

    if score == 1:
        new_level = max(0, current_level - 1)
    elif score == 2:
        new_level = current_level
    else:
        new_level = min(5, current_level + 1)

    save_progress(jp, new_level, next_review(new_level))
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
