import os
import time
import json
import datetime as dt
from collections import Counter, defaultdict

import requests

GQL_ENDPOINT = "https://shikimori.one/api/graphql"  # GraphQL endpoint :contentReference[oaicite:4]{index=4}

USER_AGENT = os.getenv("SHIKI_USER_AGENT", "shiki-dashboard (github-actions)")
NICKNAME = os.getenv("SHIKI_NICKNAME")  # обязательный
OUT_PATH = os.getenv("OUT_PATH", "data/latest.json")

SLEEP_SEC = float(os.getenv("SHIKI_SLEEP_SEC", "0.8"))  # бережно к лимитам

def gql(query: str, variables: dict | None = None, token: str | None = None) -> dict:
    headers = {
        "User-Agent": USER_AGENT,  # required by docs :contentReference[oaicite:5]{index=5}
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {"query": query, "variables": variables or {}}
    r = requests.post(GQL_ENDPOINT, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]

Q_FIND_USER = """
query($search: String!) {
  users(search: $search, limit: 50, page: 1) {
    id
    nickname
    url
  }
}
"""

Q_USER_RATES = """
query($userId: ID!, $page: PositiveInt!, $limit: PositiveInt!) {
  userRates(userId: $userId, targetType: Anime, page: $page, limit: $limit) {
    id
    status
    score
    episodes
    rewatches
    createdAt
    updatedAt
    anime {
      id
      name
      russian
      url
      kind
      status
      episodes
      duration
      nextEpisodeAt
      airedOn { year month day date }
      releasedOn { year month day date }
      genres { russian name }
      studios { name }
    }
  }
}
"""

def pick_user(users: list[dict], nickname: str) -> dict:
    if not users:
        raise RuntimeError(f"User not found by search='{nickname}'")
    low = nickname.lower()
    for u in users:
        if (u.get("nickname") or "").lower() == low:
            return u
    return users[0]

def year_from_iso8601(s: str | None) -> int | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).year
    except Exception:
        return None

def main():
    if not NICKNAME:
        raise SystemExit("Set SHIKI_NICKNAME env var (e.g. your Shikimori nickname)")

    token = os.getenv("SHIKI_BEARER_TOKEN")  # опционально (если список приватный)

    data = gql(Q_FIND_USER, {"search": NICKNAME}, token=token)
    time.sleep(SLEEP_SEC)
    user = pick_user(data["users"], NICKNAME)

    user_id = user["id"]

    rates = []
    page = 1
    limit = 50  # по схеме max 50 :contentReference[oaicite:6]{index=6}

    while True:
        d = gql(Q_USER_RATES, {"userId": user_id, "page": page, "limit": limit}, token=token)
        batch = d["userRates"]
        if not batch:
            break
        rates.extend(batch)
        page += 1
        time.sleep(SLEEP_SEC)

        # подстраховка от бесконечного цикла
        if page > 2000:
            break

    # ---- агрегаты ----
    by_status = Counter(r["status"] for r in rates)
    total_titles = len(rates)

    completed = [r for r in rates if r["status"] == "completed"]
    completed_scored = [r for r in completed if (r.get("score") or 0) > 0]
    avg_score_completed = (
        round(sum(r["score"] for r in completed_scored) / len(completed_scored), 2)
        if completed_scored else None
    )

    # score distribution 1..10 (0 игнорируем)
    score_dist = Counter()
    for r in rates:
        sc = int(r.get("score") or 0)
        if 1 <= sc <= 10:
            score_dist[sc] += 1

    total_episodes = sum(int(r.get("episodes") or 0) for r in rates)

    # время: episodes * duration (если duration есть)
    total_minutes = 0
    for r in rates:
        a = r.get("anime") or {}
        dur = a.get("duration")
        if dur and r.get("episodes"):
            total_minutes += int(r["episodes"]) * int(dur)

    # топ жанров/студий по completed
    genre_cnt = Counter()
    studio_cnt = Counter()
    for r in completed:
        a = r.get("anime") or {}
        for g in (a.get("genres") or []):
            genre_cnt[g.get("russian") or g.get("name")] += 1
        for st in (a.get("studios") or []):
            studio_cnt[st.get("name")] += 1

    top_genres = genre_cnt.most_common(12)
    top_studios = studio_cnt.most_common(12)

    # completed по годам — по updatedAt (это не “дата окончания просмотра”, но часто близко)
    by_year = Counter()
    for r in completed:
        y = year_from_iso8601(r.get("updatedAt"))
        if y:
            by_year[y] += 1
    years_sorted = sorted(by_year.items())

    # топ-20 completed по твоей оценке
    def title_key(r):
        return (int(r.get("score") or 0), year_from_iso8601(r.get("updatedAt")) or 0)

    top_completed = sorted(completed_scored, key=title_key, reverse=True)[:20]
    top_completed_out = []
    for r in top_completed:
        a = r.get("anime") or {}
        top_completed_out.append({
            "id": a.get("id"),
            "name": a.get("name"),
            "russian": a.get("russian"),
            "url": a.get("url"),
            "score": int(r.get("score") or 0),
            "year": year_from_iso8601(r.get("updatedAt")),
            "genres": [g.get("russian") or g.get("name") for g in (a.get("genres") or [])][:6],
            "studios": [s.get("name") for s in (a.get("studios") or [])][:6],
        })

    out = {
        "user": {
            "id": user_id,
            "nickname": user["nickname"],
            "url": user.get("url"),
        },
        "generated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "stats": {
            "total_titles": total_titles,
            "by_status": dict(by_status),
            "avg_score_completed": avg_score_completed,
            "total_episodes": total_episodes,
            "total_minutes_estimated": total_minutes,
        },
        "charts": {
            "statuses": dict(by_status),
            "scores": {
                "labels": [str(i) for i in range(1, 11)],
                "values": [score_dist.get(i, 0) for i in range(1, 11)],
            },
            "top_genres": {
                "labels": [k for k, _ in top_genres],
                "values": [v for _, v in top_genres],
            },
            "top_studios": {
                "labels": [k for k, _ in top_studios],
                "values": [v for _, v in top_studios],
            },
            "completed_by_year": {
                "labels": [str(y) for y, _ in years_sorted],
                "values": [v for _, v in years_sorted],
            },
        },
        "top_completed": top_completed_out,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} (rates: {len(rates)})")

if __name__ == "__main__":
    main()
