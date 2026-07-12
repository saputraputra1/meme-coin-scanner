import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

NARRATIVE_FILE = Path(__file__).parent.parent / "data" / "narratives.json"

NARRATIVES: Dict[str, List[str]] = {
    "AI": ["ai", "artificial", "gpt", "bot", "agent", "neural", "llm", "robot", "mind", "think"],
    "Dog": ["doge", "dog", "shib", "shiba", "inu", "wojak", "cheems", "floki", "puppy", "bone"],
    "Cat": ["cat", "meow", "kitty", "popcat", "mog", "kitten", "tiger", "lion"],
    "Frog": ["frog", "pepe", "kek", "toad", "ribbit"],
    "Politics": ["trump", "biden", "elon", "maga", "kamala", "president", "govern", "vote", "flag"],
    "Gamble": ["gamble", "casino", "bet", "roll", "dice", "jackpot", "gambling", "luck", "win", "fortune"],
    "Solana": ["sol", "solana", "wif", "bonk", "jup", "jupiter", "pump"],
    "Food": ["pizza", "burger", "banana", "coffee", "rice", "cake", "chocolate", "fruit", "meat"],
    "GameFi": ["game", "play", "metaverse", "nft", "pixel", "quest", "raid", "hero"],
    "Meme": ["moon", "gem", "alpha", "based", "cto", "chad", "degen", "ponzi", "rocket"],
}


def classify_narrative(name: str = "", symbol: str = "", description: str = "") -> List[str]:
    text = f"{name} {symbol} {description}".lower()
    if not text.strip():
        return []
    matched = []
    for theme, keywords in NARRATIVES.items():
        for kw in keywords:
            if kw in text:
                matched.append(theme)
                break
    return matched


def _sector_aggregate(items: List[Dict]) -> List[Dict]:
    agg = {}
    for item in items:
        tags = item.get("narratives", [])
        if not tags:
            tags = ["Other"]
        for t in tags:
            a = agg.setdefault(t, {"count": 0, "vol": 0.0, "score": 0.0, "chg_sum": 0.0, "chg_n": 0})
            a["count"] += 1
            a["vol"] += float(item.get("volume_24h", 0) or 0)
            if item.get("total_score") is not None:
                a["score"] += float(item["total_score"])
            elif item.get("score") is not None:
                a["score"] += float(item["score"].get("total_score", 0) if isinstance(item["score"], dict) else item["score"])
            chg = item.get("price_change_24h")
            if isinstance(chg, (int, float)):
                a["chg_sum"] += chg
                a["chg_n"] += 1

    sectors = []
    for theme, a in agg.items():
        sectors.append({
            "narrative": theme,
            "token_count": a["count"],
            "volume_24h": round(a["vol"], 0),
            "avg_score": round(a["score"] / a["count"], 1) if a["count"] else 0,
            "avg_change_24h": round(a["chg_sum"] / a["chg_n"], 1) if a["chg_n"] else 0,
        })

    sectors.sort(key=lambda x: x["volume_24h"], reverse=True)
    return sectors


def track_sector_momentum(items: List[Dict]) -> List[Dict]:
    sectors = _sector_aggregate(items)

    store = load_narratives()
    history = store.get("history", [])
    history.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "sectors": sectors,
    })
    store["history"] = history[-12:]
    store["latest"] = sectors
    save_narratives(store)

    return sectors


def get_narrative_momentum() -> List[Dict]:
    store = load_narratives()
    latest = store.get("latest", [])
    history = store.get("history", [])

    if len(history) >= 2:
        prev = history[-2].get("sectors", [])
        prev_map = {s["narrative"]: s for s in prev}
        for s in latest:
            p = prev_map.get(s["narrative"])
            s["volume_delta"] = round(s["volume_24h"] - p["volume_24h"], 0) if p else 0
            s["change_delta"] = round(s["avg_change_24h"] - p["avg_change_24h"], 1) if p else 0
    else:
        for s in latest:
            s["volume_delta"] = 0
            s["change_delta"] = 0

    return latest


def load_narratives() -> Dict:
    if NARRATIVE_FILE.exists():
        try:
            data = json.loads(NARRATIVE_FILE.read_text())
            data.setdefault("history", [])
            data.setdefault("latest", [])
            return data
        except Exception:
            pass
    return {"history": [], "latest": []}


def save_narratives(store: Dict):
    NARRATIVE_FILE.parent.mkdir(exist_ok=True, parents=True)
    NARRATIVE_FILE.write_text(json.dumps(store, indent=2, ensure_ascii=False, default=str))
