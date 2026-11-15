"""La boucle agentique : penser -> agir (outils) -> observer -> recommencer."""
import json
import os
import platform
import re
import unicodedata
from datetime import datetime

from .llm import LLMError

SYSTEM_PROMPT = """Tu es AgentOS, un agent IA autonome qui accomplit des missions de A à Z \
sur l'ordinateur de l'utilisateur, à l'aide d'outils.

MÉTHODE
1. Comprends la mission. Si un point vraiment bloquant est ambigu, utilise ask_user ; \
sinon choisis l'interprétation la plus raisonnable et note-la.
2. Établis un plan avec l'outil `plan` (3 à 10 étapes concrètes et vérifiables).
3. Exécute les étapes une par une avec les outils, et mets le plan à jour (update_step).
4. VÉRIFIE ton travail : exécute le code, relis les fichiers, teste le résultat. \
Ne déclare jamais une chose faite sans l'avoir constatée.
5. Termine avec `finish` : résumé clair de ce qui a été fait, où sont les résultats, \
ce qui reste éventuellement à faire.

RÈGLES
- Tu travailles dans l'espace de travail : {workspace}
- N'invente jamais un résultat. Si un outil échoue, lis l'erreur, corrige, essaie autre \
chose (pas plus de 3 essais sur la même approche).
- Avant une action irréversible (supprimer, envoyer, payer, publier), demande confirmation.
- Pour une grosse sous-tâche indépendante, tu peux utiliser `delegate`.
- Mémorise avec `remember` ce qui servira aux prochaines missions (préférences, chemins, \
identifiants de projets — jamais de mots de passe).
- Sois concis dans tes messages ; le travail se voit dans les outils.

CONTEXTE
- Système : {os} | Date : {date} | Mode : {mode}
- Mémoire long terme (récente) :
{memory}
"""

C = {"dim": "\033[2m", "cyan": "\033[36m", "green": "\033[32m", "red": "\033[31m",
     "yellow": "\033[33m", "bold": "\033[1m", "end": "\033[0m"}
if os.name == "nt":
    os.system("")  # active les couleurs ANSI sous Windows


def _short(v, n=160):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = s.replace("\n", " ⏎ ")
    return s if len(s) <= n else s[:n] + "…"


class Agent:
    def __init__(self, llm, toolbox, memory, max_steps=60, reports_dir="rapports",
                 verbose=True, name="AgentOS"):
        self.llm = llm
        self.tools = toolbox
        self.memory = memory
        self.max_steps = max_steps
        self.reports_dir = reports_dir
        self.verbose = verbose
        self.name = name
        self.tokens = {"input": 0, "output": 0}
        self.journal = []

    def _p(self, text, color=None):
        if self.verbose:
            pre = "    " * self.tools.depth
            print(pre + (C[color] + text + C["end"] if color else text), flush=True)

    def _system(self):
        return SYSTEM_PROMPT.format(
            workspace=self.tools.workspace,
            os=f"{platform.system()} {platform.release()}",
            date=datetime.now().strftime("%Y-%m-%d %H:%M"),
            mode="interactif (un humain peut répondre)" if self.tools.interactive
            else "autonome (personne ne peut répondre : décide seul)",
            memory=self.memory.as_text(),
        )

    def run(self, mission, history=None):
        """Exécute une mission. `history` permet de poursuivre une conversation."""
        messages = history if history is not None else []
        messages.append({"role": "user", "text": mission})
        tools = self.tools.schemas()
        self.tools.finished = None
        start = datetime.now()
        self._p(f"\n🚀 Mission : {_short(mission, 300)}", "bold")

        status, final_text = "terminée", ""
        for step in range(1, self.max_steps + 1):
            try:
                resp = self.llm.chat(self._system(), messages, tools)
            except LLMError as e:
                self._p(f"❌ Erreur du modèle : {e}", "red")
                status, final_text = "erreur", str(e)
                break
            self.tokens["input"] += resp["usage"]["input"]
            self.tokens["output"] += resp["usage"]["output"]
            messages.append({"role": "assistant", "text": resp["text"],
                             "tool_calls": resp["tool_calls"]})
            if resp["text"].strip():
                self._p(f"💭 {resp['text'].strip()}", "cyan")
                final_text = resp["text"].strip()

            if not resp["tool_calls"]:  # le modèle a fini de parler
                break

            results = []
            for call in resp["tool_calls"]:
                self._p(f"🔧 {call['name']}({_short(call['input'])})", "yellow")
                output, is_err = self.tools.call(call["name"], call["input"])
                self._p(f"   ↳ {_short(output, 300)}", "red" if is_err else "dim")
                results.append({"id": call["id"], "name": call["name"],
                                "output": output, "is_error": is_err})
                self.journal.append({"step": step, "tool": call["name"],
                                     "input": call["input"], "output": output[:2000],
                                     "error": is_err})
            messages.append({"role": "tool", "results": results})

            if self.tools.finished is not None:
                final_text = self.tools.finished
                break
        else:
            status = "interrompue (nombre maximal d'étapes atteint)"

        duration = (datetime.now() - start).total_seconds()
        self._p(f"\n🏁 Mission {status} en {duration:.0f}s "
                f"({self.tokens['input']} jetons entrée / {self.tokens['output']} sortie)",
                "green" if status == "terminée" else "red")
        if final_text:
            self._p(f"\n📋 {final_text}\n", "bold")
        report = self._write_report(mission, status, final_text, duration)
        return {"status": status, "summary": final_text, "report": report,
                "messages": messages, "tokens": dict(self.tokens)}

    def _write_report(self, mission, status, summary, duration):
        if self.tools.depth > 0:
            return None
        os.makedirs(self.reports_dir, exist_ok=True)
        plain = unicodedata.normalize("NFKD", mission.lower()).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-z0-9]+", "-", plain)[:40].strip("-") or "mission"
        path = os.path.join(self.reports_dir,
                            f"{datetime.now():%Y%m%d-%H%M%S}_{slug}.md")
        plan = "\n".join(f"- [{'x' if s['status'] == 'fait' else ' '}] {s['step']} "
                         f"({s['status']})" for s in self.tools.plan) or "(aucun plan)"
        steps = "\n".join(f"{i}. `{j['tool']}` {_short(j['input'], 120)}"
                          + (" ❌" if j["error"] else "")
                          for i, j in enumerate(self.journal, 1))
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Rapport de mission\n\n**Date** : {datetime.now():%Y-%m-%d %H:%M}  \n"
                    f"**Statut** : {status}  \n**Durée** : {duration:.0f}s  \n"
                    f"**Jetons** : {self.tokens['input']} entrée / "
                    f"{self.tokens['output']} sortie\n\n"
                    f"## Mission\n\n{mission}\n\n## Résultat\n\n{summary}\n\n"
                    f"## Plan\n\n{plan}\n\n## Actions effectuées\n\n{steps}\n")
        self._p(f"📝 Rapport : {path}", "dim")
        return path
