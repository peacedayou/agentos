"""Les "mains" de l'agent : terminal, fichiers, web, plan, mémoire, sous-agents."""
import html
import os
import re
import subprocess
import urllib.request
from html.parser import HTMLParser

MAX_OUTPUT = 12000

DANGEROUS = [
    r"\brm\s+(-\w*\s+)*-\w*[rf]", r"\bsudo\b", r"\bmkfs", r"\bdd\s+if=",
    r"\bshutdown\b", r"\breboot\b", r":\(\)\s*\{", r"chmod\s+-R\s+777\s+/",
    r">\s*/dev/sd", r"(curl|wget)[^|]*\|\s*(ba|z)?sh", r"git\s+push\s+.*--force",
    r"\bdel\s+/[sq]", r"\bformat\s+[a-z]:", r"\brmdir\s+/s", r"Remove-Item.*-Recurse",
    r"\bdrop\s+(table|database)\b", r"\bkill\s+-9\b", r"\bpip\s+uninstall\b",
]


def _truncate(text, limit=MAX_OUTPUT):
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + f"\n\n[... {len(text) - limit} caractères coupés ...]\n\n" + text[-half:]


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


class Toolbox:
    def __init__(self, workspace, memory, approval="dangereux", interactive=True,
                 allow_outside=False, agent_factory=None, depth=0, log=print):
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        self.memory = memory
        self.approval = approval          # "auto" | "dangereux" | "tout"
        self.interactive = interactive    # un humain peut-il répondre ?
        self.allow_outside = allow_outside
        self.agent_factory = agent_factory
        self.depth = depth
        self.log = log
        self.plan = []
        self.finished = None

    # ------------------------------------------------------------------ utils
    def _path(self, p):
        # realpath : un lien symbolique placé dans l'espace de travail ne permet pas d'en sortir.
        full = os.path.realpath(os.path.join(self.workspace, os.path.expanduser(p)))
        racine = os.path.realpath(self.workspace)
        try:
            dedans = os.path.commonpath([full, racine]) == racine
        except ValueError:  # Windows : autre lecteur que l'espace de travail
            dedans = False
        if not self.allow_outside and not dedans:
            raise PermissionError(f"Accès refusé hors de l'espace de travail : {p}")
        return full

    def _approve(self, action, dangerous):
        if self.approval == "auto":
            return True
        if self.approval == "dangereux" and not dangerous:
            return True
        if not self.interactive:
            return False
        ans = input(f"\n  ⚠️  Autoriser : {action} ? [o/N] ").strip().lower()
        return ans in ("o", "oui", "y", "yes")

    # ------------------------------------------------------------------ outils
    def t_plan(self, steps):
        self.plan = [{"step": s, "status": "à_faire"} for s in steps]
        return "Plan enregistré :\n" + self._plan_text()

    def t_update_step(self, index, status, note=""):
        if not 1 <= index <= len(self.plan):
            return f"Index invalide (1 à {len(self.plan)})."
        self.plan[index - 1]["status"] = status
        if note:
            self.plan[index - 1]["note"] = note
        return self._plan_text()

    def _plan_text(self):
        icon = {"à_faire": "⬜", "en_cours": "🔄", "fait": "✅", "échec": "❌"}
        return "\n".join(f"{icon.get(s['status'], '•')} {i}. {s['step']}"
                         for i, s in enumerate(self.plan, 1))

    def t_run_command(self, command, timeout=300):
        dangerous = any(re.search(p, command, re.I) for p in DANGEROUS)
        if not self._approve(f"commande « {command} »", dangerous):
            return "REFUSÉ : commande non autorisée (jugée risquée). Trouve une autre approche."
        try:
            # shell=True est voulu : l'agent exécute des commandes shell complètes. La garde est
            # _approve() (motifs DANGEROUS + confirmation) ; le mode « auto » la désactive : à réserver
            # à un bac à sable jetable.
            r = subprocess.run(command, shell=True, cwd=self.workspace, capture_output=True,
                               text=True, timeout=timeout, encoding="utf-8", errors="replace")
            out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
            return _truncate(f"[code retour {r.returncode}]\n{out.strip()}")
        except subprocess.TimeoutExpired:
            return f"ERREUR : délai dépassé ({timeout}s)."

    def t_read_file(self, path, offset=1, limit=400):
        full = self._path(path)
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        chunk = lines[offset - 1: offset - 1 + limit]
        body = "".join(f"{i:>5}  {l}" for i, l in enumerate(chunk, offset))
        more = f"\n[{len(lines)} lignes au total]" if len(lines) > offset - 1 + limit else ""
        return _truncate(body + more)

    def t_write_file(self, path, content):
        full = self._path(path)
        if (os.path.exists(full) and self.approval == "tout"
                and not self._approve(f"écraser {path}", True)):
            return "REFUSÉ : écrasement non autorisé."
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Fichier écrit : {path} ({len(content)} caractères)"

    def t_edit_file(self, path, old, new):
        full = self._path(path)
        with open(full, encoding="utf-8") as f:
            text = f.read()
        n = text.count(old)
        if n != 1:
            return f"ERREUR : le texte à remplacer apparaît {n} fois (il doit être unique)."
        with open(full, "w", encoding="utf-8") as f:
            f.write(text.replace(old, new))
        return f"Fichier modifié : {path}"

    def t_list_dir(self, path=".", recursive=False):
        full = self._path(path)
        rows = []
        if recursive:
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                           ("node_modules", "__pycache__", "venv", ".venv")]
                for name in files:
                    rows.append(os.path.relpath(os.path.join(root, name), full))
                if len(rows) > 500:
                    rows.append("[... tronqué]")
                    break
        else:
            for name in sorted(os.listdir(full)):
                p = os.path.join(full, name)
                rows.append(name + ("/" if os.path.isdir(p) else f"  ({os.path.getsize(p)} o)"))
        return "\n".join(rows) or "(dossier vide)"

    def t_web_fetch(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AgentOS"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8",
                                           errors="replace")
        if "<html" in raw[:2000].lower():
            ex = _TextExtractor()
            ex.feed(raw)
            raw = html.unescape("".join(ex.parts))
        text = re.sub(r"\n\s*\n+", "\n\n", raw)
        return _truncate(text.strip(), 15000)

    def t_remember(self, note, tags=None):
        self.memory.add(note, tags)
        return "Mémorisé."

    def t_recall(self, query):
        hits = self.memory.search(query)
        return "\n".join(f"- [{h['date'][:10]}] {h['note']}" for h in hits) or "Aucun souvenir."

    def t_ask_user(self, question):
        if not self.interactive:
            return ("Aucun humain disponible (mode autonome). Choisis l'option la plus "
                    "raisonnable, note ton choix dans le rapport final et continue.")
        return input(f"\n  ❓ {question}\n  > ").strip() or "(pas de réponse)"

    def t_delegate(self, mission):
        if self.agent_factory is None or self.depth >= 1:
            return "Délégation indisponible ici : fais la sous-tâche toi-même."
        sub = self.agent_factory(depth=self.depth + 1)
        result = sub.run(mission)
        return f"Rapport du sous-agent :\n{result['summary']}"

    def t_finish(self, summary):
        self.finished = summary
        return "Mission terminée."

    # ---------------------------------------------------------------- schémas
    def schemas(self):
        S = lambda props, req: {"type": "object", "properties": props, "required": req}
        string = {"type": "string"}
        tools = [
            ("plan", "Définit le plan de la mission (liste d'étapes concrètes). À appeler "
                     "au début, et à nouveau si le plan change.",
             S({"steps": {"type": "array", "items": string}}, ["steps"])),
            ("update_step", "Met à jour le statut d'une étape du plan (numérotée à partir de 1).",
             S({"index": {"type": "integer"},
                "status": {"type": "string", "enum": ["à_faire", "en_cours", "fait", "échec"]},
                "note": string}, ["index", "status"])),
            ("run_command", "Exécute une commande dans le terminal (dans l'espace de travail). "
                            "Sert à lancer du code, installer, tester, manipuler des fichiers, git...",
             S({"command": string, "timeout": {"type": "integer"}}, ["command"])),
            ("read_file", "Lit un fichier texte (avec numéros de ligne).",
             S({"path": string, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
               ["path"])),
            ("write_file", "Crée ou remplace entièrement un fichier.",
             S({"path": string, "content": string}, ["path", "content"])),
            ("edit_file", "Remplace un passage précis (unique) d'un fichier existant.",
             S({"path": string, "old": string, "new": string}, ["path", "old", "new"])),
            ("list_dir", "Liste le contenu d'un dossier.",
             S({"path": string, "recursive": {"type": "boolean"}}, [])),
            ("web_fetch", "Télécharge une page web et renvoie son texte.",
             S({"url": string}, ["url"])),
            ("remember", "Enregistre une information utile dans la mémoire long terme.",
             S({"note": string, "tags": {"type": "array", "items": string}}, ["note"])),
            ("recall", "Cherche dans la mémoire long terme.", S({"query": string}, ["query"])),
            ("ask_user", "Pose une question à l'utilisateur (seulement si c'est vraiment bloquant).",
             S({"question": string}, ["question"])),
            ("delegate", "Confie une sous-tâche autonome et bien définie à un sous-agent "
                         "qui repart d'un contexte vierge et renvoie un rapport.",
             S({"mission": string}, ["mission"])),
            ("finish", "Termine la mission avec un résumé final : ce qui a été fait, où se "
                       "trouvent les résultats, ce qui reste éventuellement à faire.",
             S({"summary": string}, ["summary"])),
        ]
        return [{"name": n, "description": d, "parameters": p} for n, d, p in tools]

    def call(self, name, args):
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return f"ERREUR : outil inconnu « {name} ».", True
        try:
            return str(fn(**args)), False
        except TypeError as e:
            return f"ERREUR d'arguments : {e}", True
        except Exception as e:  # l'agent lit l'erreur et corrige
            return f"ERREUR : {type(e).__name__}: {e}", True
