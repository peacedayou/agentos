"""Point d'entrée : python -m agentos <commande>

  run "mission"        exécute une mission de A à Z
  run -f mission.md    mission lue depuis un fichier
  chat                 conversation continue avec l'agent (il garde le contexte)
  daemon               mode système : exécute les missions déposées / planifiées
  memoire              affiche la mémoire long terme
"""
import argparse
import os
import sys

from .core import build_agent, load_config
from .daemon import run_daemon
from .memory import Memory


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="agentos", description="AgentOS — agent IA autonome")
    ap.add_argument("--config", help="chemin vers config.json")
    ap.add_argument("--provider", help="anthropic | openai | ollama | mock")
    ap.add_argument("--model")
    ap.add_argument("--auto", action="store_true",
                    help="aucune demande d'autorisation (à utiliser avec prudence)")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("mission", nargs="?")
    r.add_argument("-f", "--fichier")
    r.add_argument("--autonome", action="store_true",
                   help="ne pose aucune question, décide seul")
    sub.add_parser("chat")
    dm = sub.add_parser("daemon")
    dm.add_argument("--une-fois", action="store_true")
    sub.add_parser("memoire")
    a = ap.parse_args()

    cfg = load_config(a.config)
    if a.provider:
        cfg["provider"] = a.provider
    if a.model:
        cfg["model"] = a.model
    if a.auto:
        cfg["approval"] = "auto"

    if a.cmd == "run":
        mission = a.mission
        if a.fichier:
            with open(a.fichier, encoding="utf-8") as f:
                mission = f.read()
        if not mission:
            ap.error("donne une mission entre guillemets ou -f fichier.md")
        res = build_agent(cfg, interactive=not a.autonome).run(mission)
        sys.exit(0 if res["status"] == "terminée" else 1)

    elif a.cmd == "chat":
        agent = build_agent(cfg)
        history = []
        print("💬 AgentOS — tape ta demande (ou 'quitter').")
        while True:
            try:
                msg = input("\nToi > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if msg.lower() in ("quitter", "exit", "quit"):
                break
            if msg:
                history = agent.run(msg, history)["messages"]

    elif a.cmd == "daemon":
        run_daemon(cfg, once=a.une_fois)

    elif a.cmd == "memoire":
        print(Memory(cfg["memory_file"]).as_text(100))

    else:
        ap.print_help()


if __name__ == "__main__":
    main()
