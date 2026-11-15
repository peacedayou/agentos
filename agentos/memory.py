"""Mémoire persistante : l'agent se souvient d'une mission à l'autre."""
import json
import os
import re
from datetime import datetime


class Memory:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _all(self):
        if not os.path.exists(self.path):
            return []
        items = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return items

    def add(self, note, tags=None):
        item = {"date": datetime.now().isoformat(timespec="seconds"),
                "note": note, "tags": tags or []}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def search(self, query, limit=10):
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        scored = []
        for it in self._all():
            hay = (it["note"] + " " + " ".join(it.get("tags", []))).lower()
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, it))
        scored.sort(key=lambda x: (-x[0], x[1]["date"]), reverse=False)
        return [it for _, it in scored[:limit]]

    def recent(self, n=15):
        return self._all()[-n:]

    def as_text(self, n=15):
        items = self.recent(n)
        if not items:
            return "(aucun souvenir pour l'instant)"
        return "\n".join(f"- [{i['date'][:10]}] {i['note']}" for i in items)
