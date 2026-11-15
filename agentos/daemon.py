"""Mode « système » : tourne en continu et exécute les missions automatiquement.

- missions/a_faire/*.md  -> chaque fichier déposé est exécuté puis rangé dans
                            missions/terminees/ (ou missions/echecs/)
- missions/planning.json -> missions récurrentes, par ex. :
  [{"nom": "veille", "toutes_les_minutes": 1440, "a_partir_de": "08:00",
    "mission": "Résume les nouvelles IA du jour dans veille/AAAA-MM-JJ.md"}]
"""
import json
import os
import shutil
import time
from datetime import datetime

from .core import build_agent


def _dirs(cfg):
    base = cfg["missions_dir"]
    d = {k: os.path.join(base, k) for k in ("a_faire", "en_cours", "terminees", "echecs")}
    for p in d.values():
        os.makedirs(p, exist_ok=True)
    d["planning"] = os.path.join(base, "planning.json")
    d["etat"] = os.path.join(base, ".etat_planning.json")
    return d


def _run_file(cfg, d, name):
    src = os.path.join(d["a_faire"], name)
    running = os.path.join(d["en_cours"], name)
    shutil.move(src, running)
    with open(running, encoding="utf-8") as f:
        mission = f.read().strip()
    print(f"\n📥 [{datetime.now():%H:%M:%S}] Nouvelle mission : {name}")
    try:
        res = build_agent(cfg, interactive=False).run(mission)
        ok = res["status"] == "terminée"
    except Exception as e:  # le démon ne doit jamais tomber
        print(f"❌ Plantage : {e}")
        res, ok = {"summary": str(e), "report": None}, False
    dest = os.path.join(d["terminees" if ok else "echecs"],
                        f"{datetime.now():%Y%m%d-%H%M%S}_{name}")
    shutil.move(running, dest)
    with open(dest, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n## Résultat\n{res['summary']}\n\nRapport : {res.get('report')}\n")


def _due(entry, last):
    now = datetime.now()
    start = entry.get("a_partir_de")
    if start and now.strftime("%H:%M") < start:
        return False
    if last is None:
        return True
    return (now.timestamp() - last) >= entry.get("toutes_les_minutes", 60) * 60


def _run_schedule(cfg, d):
    if not os.path.exists(d["planning"]):
        return
    try:
        with open(d["planning"], encoding="utf-8") as f:
            entries = json.load(f)
        state = {}
        if os.path.exists(d["etat"]):
            with open(d["etat"], encoding="utf-8") as f:
                state = json.load(f)
    except json.JSONDecodeError as e:
        print(f"⚠️  planning.json invalide : {e}")
        return
    for e in entries:
        if e.get("actif", True) and _due(e, state.get(e["nom"])):
            print(f"\n⏰ [{datetime.now():%H:%M:%S}] Mission planifiée : {e['nom']}")
            state[e["nom"]] = time.time()
            with open(d["etat"], "w", encoding="utf-8") as f:
                json.dump(state, f)
            try:
                build_agent(cfg, interactive=False).run(e["mission"])
            except Exception as ex:
                print(f"❌ Plantage : {ex}")


def run_daemon(cfg, once=False):
    d = _dirs(cfg)
    print(f"🟢 AgentOS en service. Dépose des missions (.md/.txt) dans :\n   {d['a_faire']}\n"
          f"   Missions récurrentes : {d['planning']}\n   Ctrl+C pour arrêter.")
    while True:
        try:
            for name in sorted(os.listdir(d["a_faire"])):
                if name.lower().endswith((".md", ".txt")):
                    _run_file(cfg, d, name)
            _run_schedule(cfg, d)
            if once:
                return
            time.sleep(cfg["poll_seconds"])
        except KeyboardInterrupt:
            print("\n🔴 AgentOS arrêté.")
            return
