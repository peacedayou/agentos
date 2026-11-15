"""Connecteurs vers les modèles d'IA (le "cerveau" de l'agent).

Format interne des messages (indépendant du fournisseur) :
  {"role": "user", "text": "..."}
  {"role": "assistant", "text": "...", "tool_calls": [{"id", "name", "input"}]}
  {"role": "tool", "results": [{"id", "name", "output", "is_error"}]}

Aucune dépendance externe : tout passe par urllib.
"""
import json
import os
import time
import urllib.error
import urllib.request


class LLMError(Exception):
    pass


def _post(url, headers, payload, timeout=600, retries=4):
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (408, 429, 500, 502, 503, 504, 529) and attempt < retries - 1:
                wait = 5 * (2 ** attempt)
                print(f"  [API] erreur {e.code}, nouvel essai dans {wait}s...")
                time.sleep(wait)
                continue
            raise LLMError(f"HTTP {e.code} : {body[:800]}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise LLMError(f"Connexion impossible : {e}")


# --------------------------------------------------------------------------- #
# Anthropic (Claude)
# --------------------------------------------------------------------------- #
class AnthropicLLM:
    def __init__(self, model, api_key=None, max_tokens=8000,
                 base_url="https://api.anthropic.com"):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise LLMError("Clé manquante : définis la variable ANTHROPIC_API_KEY "
                           "ou 'api_key' dans config.json")

    @staticmethod
    def _convert(messages):
        out = []
        for m in messages:
            if m["role"] == "user":
                role, content = "user", [{"type": "text", "text": m["text"]}]
            elif m["role"] == "assistant":
                role, content = "assistant", []
                if m.get("text"):
                    content.append({"type": "text", "text": m["text"]})
                for c in m.get("tool_calls", []):
                    content.append({"type": "tool_use", "id": c["id"],
                                    "name": c["name"], "input": c["input"]})
            else:  # résultats d'outils
                role = "user"
                content = [{"type": "tool_result", "tool_use_id": r["id"],
                            "content": r["output"] or "(vide)",
                            "is_error": bool(r.get("is_error"))}
                           for r in m["results"]]
            if out and out[-1]["role"] == role:  # l'API exige l'alternance
                out[-1]["content"].extend(content)
            else:
                out.append({"role": role, "content": content})
        return out

    def chat(self, system, messages, tools):
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": self._convert(messages),
            "tools": [{"name": t["name"], "description": t["description"],
                       "input_schema": t["parameters"]} for t in tools],
        }
        r = _post(f"{self.base_url}/v1/messages", {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, payload)
        blocks = r.get("content", [])
        usage = r.get("usage", {})
        return {
            "text": "".join(b.get("text", "") for b in blocks if b["type"] == "text"),
            "tool_calls": [{"id": b["id"], "name": b["name"], "input": b.get("input", {})}
                           for b in blocks if b["type"] == "tool_use"],
            "usage": {"input": usage.get("input_tokens", 0),
                      "output": usage.get("output_tokens", 0)},
        }


# --------------------------------------------------------------------------- #
# Compatible OpenAI : OpenAI, Ollama (local, gratuit), LM Studio, Mistral, Groq...
# --------------------------------------------------------------------------- #
class OpenAICompatLLM:
    def __init__(self, model, api_key=None, base_url="https://api.openai.com/v1",
                 max_tokens=None):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "none")
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens

    @staticmethod
    def _convert(system, messages):
        out = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["text"]})
            elif m["role"] == "assistant":
                msg = {"role": "assistant", "content": m.get("text") or ""}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{
                        "id": c["id"], "type": "function",
                        "function": {"name": c["name"],
                                     "arguments": json.dumps(c["input"], ensure_ascii=False)},
                    } for c in m["tool_calls"]]
                out.append(msg)
            else:
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r["id"],
                                "content": r["output"] or "(vide)"})
        return out

    def chat(self, system, messages, tools):
        payload = {
            "model": self.model,
            "messages": self._convert(system, messages),
            "tools": [{"type": "function", "function": {
                "name": t["name"], "description": t["description"],
                "parameters": t["parameters"]}} for t in tools],
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        r = _post(f"{self.base_url}/chat/completions", {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }, payload)
        msg = r["choices"][0]["message"]
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            args = c["function"].get("arguments") or "{}"
            try:
                parsed = json.loads(args) if isinstance(args, str) else args
            except json.JSONDecodeError:
                parsed = {"_raw": args}
            calls.append({"id": c.get("id") or f"call_{i}",
                          "name": c["function"]["name"], "input": parsed})
        usage = r.get("usage", {})
        return {"text": msg.get("content") or "", "tool_calls": calls,
                "usage": {"input": usage.get("prompt_tokens", 0),
                          "output": usage.get("completion_tokens", 0)}}


# --------------------------------------------------------------------------- #
# Mode démo (sans clé ni Internet) : vérifie que toute la mécanique fonctionne
# --------------------------------------------------------------------------- #
class MockLLM:
    SCRIPT = [
        ("Je planifie la mission.", [("plan", {"steps": [
            "Créer un script Python de démonstration",
            "L'exécuter pour vérifier qu'il fonctionne",
            "Mémoriser le résultat et terminer"]})]),
        ("J'écris le script.", [("update_step", {"index": 1, "status": "en_cours"}),
                                ("write_file", {"path": "demo/bonjour.py",
                                                "content": "print('Bonjour depuis AgentOS !')\n"})]),
        ("Je teste le script.", [("update_step", {"index": 1, "status": "fait"}),
                                 ("run_command", {"command": "python demo/bonjour.py"})]),
        ("Ça marche, je mémorise.", [("update_step", {"index": 2, "status": "fait"}),
                                     ("remember", {"note": "Le mode démo d'AgentOS fonctionne."})]),
        ("", [("update_step", {"index": 3, "status": "fait"}),
              ("finish", {"summary": "Script demo/bonjour.py créé et testé avec succès."})]),
    ]

    def __init__(self, *a, **k):
        pass

    def chat(self, system, messages, tools):
        turn = sum(1 for m in messages if m["role"] == "assistant")
        if turn >= len(self.SCRIPT):
            return {"text": "Terminé.", "tool_calls": [], "usage": {"input": 0, "output": 0}}
        text, calls = self.SCRIPT[turn]
        return {"text": text,
                "tool_calls": [{"id": f"mock_{turn}_{i}", "name": n, "input": a}
                               for i, (n, a) in enumerate(calls)],
                "usage": {"input": 0, "output": 0}}


def build_llm(cfg):
    p = cfg["provider"]
    if p == "anthropic":
        return AnthropicLLM(cfg["model"], cfg.get("api_key"), cfg.get("max_tokens", 8000))
    if p == "openai":
        return OpenAICompatLLM(cfg["model"], cfg.get("api_key"),
                               cfg.get("base_url", "https://api.openai.com/v1"),
                               cfg.get("max_tokens"))
    if p == "ollama":
        return OpenAICompatLLM(cfg["model"], "ollama",
                               cfg.get("base_url", "http://localhost:11434/v1"))
    if p == "mock":
        return MockLLM()
    raise LLMError(f"Fournisseur inconnu : {p} (anthropic, openai, ollama, mock)")
