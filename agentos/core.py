"""Configuration et assemblage des pièces (cerveau + mains + mémoire)."""
import json
import os

from .agent import Agent
from .llm import build_llm
from .memory import Memory
from .tools import Toolbox

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DEFAULTS = {
    "provider": "anthropic",            # anthropic | openai | ollama | mock
    "model": "claude-sonnet-5-5",
    "api_key": None,                    # sinon variable d'environnement
    "base_url": None,
    "max_tokens": 8000,
    "max_steps": 60,
    "workspace": "espace_de_travail",
    "approval": "dangereux",            # auto | dangereux | tout
    "allow_outside_workspace": False,
    "memory_file": "donnees/memoire.jsonl",
    "reports_dir": "rapports",
    "missions_dir": "missions",
    "poll_seconds": 10,
}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    path = path or os.path.join(ROOT, "config.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update({k: v for k, v in json.load(f).items() if not k.startswith("_")})
    if cfg.get("base_url") is None:
        cfg.pop("base_url")
    for key in ("workspace", "memory_file", "reports_dir", "missions_dir"):
        if not os.path.isabs(cfg[key]):
            cfg[key] = os.path.join(ROOT, cfg[key])
    return cfg


def build_agent(cfg, interactive=True, verbose=True, depth=0):
    llm = build_llm(cfg)
    memory = Memory(cfg["memory_file"])

    def factory(depth):
        return build_agent(cfg, interactive=False, verbose=verbose, depth=depth)

    toolbox = Toolbox(cfg["workspace"], memory, approval=cfg["approval"],
                      interactive=interactive,
                      allow_outside=cfg["allow_outside_workspace"],
                      agent_factory=factory, depth=depth)
    return Agent(llm, toolbox, memory, max_steps=cfg["max_steps"],
                 reports_dir=cfg["reports_dir"], verbose=verbose)
