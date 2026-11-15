# AgentOS

[![CI](https://github.com/peacedayou/agentos/actions/workflows/ci.yml/badge.svg)](https://github.com/peacedayou/agentos/actions/workflows/ci.yml) : système d'agent IA autonome

Tu donnes une **mission précise**. AgentOS la réalise **de A à Z**, comme Claude en mode agent :

```
Mission ─► 🧠 Planifie ─► 🔧 Agit (terminal, fichiers, web) ─► 👀 Observe le résultat
              ▲                                                        │
              └──────────── corrige / continue ◄───────────────────────┘
                                   │
                                   ▼  quand c'est vérifié
                          ✅ finish + 📝 rapport + 🧠 mémoire
```

Aucune bibliothèque à installer : seulement **Python 3.9 ou plus récent**.

---

## 1. Installation (5 minutes)

1. Installe Python : https://www.python.org/downloads/ (sous Windows, coche **« Add Python to PATH »**).
2. Décompresse le dossier `AgentOS` où tu veux.
3. Choisis le cerveau de l'agent dans `config.json` :

| Option | `provider` | `model` | Clé |
|---|---|---|---|
| **Claude** (recommandé, le plus fiable en agent) | `anthropic` | `claude-sonnet-5-5` ou `claude-opus-5-5` | https://console.anthropic.com |
| OpenAI | `openai` | ex. `gpt-4.1` | https://platform.openai.com |
| **Local et gratuit** (Ollama) | `ollama` | ex. `qwen2.5:14b` ou `llama3.1` | aucune ; installe https://ollama.com puis `ollama pull qwen2.5:14b` |
| Démo, sans IA | `mock` | — | aucune |

4. Donne ta clé **en variable d'environnement** (ne l'écris jamais dans `config.json` : ce fichier est suivi par Git et finirait dans un dépôt public) :
   - Windows : `setx ANTHROPIC_API_KEY "sk-ant-..."` (puis rouvre le terminal)
   - Mac/Linux : `export ANTHROPIC_API_KEY="sk-ant-..."` (dans `~/.bashrc` ou `~/.zshrc`)

5. Vérifie que tout marche : `python -m agentos --provider mock run "test"`

---

## 2. Utilisation

Ouvre un terminal **dans le dossier AgentOS** :

```bash
# Une mission, de A à Z
python -m agentos run "Crée un site web vitrine pour une boulangerie dans le dossier boulangerie/, avec une page d'accueil, un menu et un formulaire de contact. Teste que le HTML est valide."

# Mission longue écrite dans un fichier
python -m agentos run -f exemples/mission_rapport_csv.md

# Mode 100 % autonome : aucune question posée, il décide seul
python -m agentos run --autonome -f ma_mission.md

# Conversation continue (il garde le contexte entre tes messages)
python -m agentos chat

# MODE SYSTÈME : tourne en continu et exécute les missions automatiquement
python -m agentos daemon

# Voir ce dont il se souvient
python -m agentos memoire
```

Raccourcis : double-clique sur `lancer.bat` (Windows) ou lance `./lancer.sh` (Mac/Linux).

---

## 3. Mode système (automatisation complète)

Lance `python -m agentos daemon`, puis :

- **Missions ponctuelles** : dépose un fichier `.md` ou `.txt` dans `missions/a_faire/`. Il est exécuté, puis rangé dans `missions/terminees/` (ou `missions/echecs/`) avec le résultat ajouté à la fin.
- **Missions récurrentes** : renomme `exemples/planning.json` en `missions/planning.json` et adapte-le :

```json
[
  {"nom": "rapport-quotidien", "toutes_les_minutes": 1440, "a_partir_de": "08:00",
   "mission": "Analyse les fichiers CSV de donnees/ventes/ et écris rapports/ventes_AAAA-MM-JJ.md"}
]
```

Pour qu'il démarre avec l'ordinateur :
- **Windows** : Planificateur de tâches → Créer une tâche → Déclencheur « À l'ouverture de session » → Action : `pythonw -m agentos daemon`, avec « Commencer dans » = le dossier AgentOS.
- **Mac/Linux** : ajoute `@reboot cd /chemin/AgentOS && python3 -m agentos daemon >> agentos.log 2>&1` via `crontab -e`.

---

## 4. Écrire une bonne mission (c'est là que tout se joue)

Une mission précise donne un résultat précis. Utilise ce modèle :

```markdown
OBJECTIF : ce que je veux obtenir, en une phrase.
CONTEXTE : où sont les fichiers, pour qui c'est, contraintes.
ÉTAPES ATTENDUES (facultatif) : 1. ... 2. ... 3. ...
LIVRABLE : nom et emplacement exact du ou des fichiers à produire.
CRITÈRES DE RÉUSSITE : comment vérifier que c'est bien fait (tests, contrôles).
INTERDIT : ce qu'il ne doit pas faire.
```

Exemples prêts à l'emploi dans `exemples/`.

---

## 5. Sécurité

| Réglage `approval` | Comportement |
|---|---|
| `dangereux` (défaut) | Demande ton accord avant une commande risquée (`rm -rf`, `sudo`, `format`, `git push --force`...). En mode autonome, ces commandes sont **refusées**. |
| `tout` | Demande ton accord pour chaque commande et chaque écrasement de fichier. |
| `auto` | Ne demande rien. À réserver à un environnement isolé (machine virtuelle). |

- L'agent ne travaille **que dans `espace_de_travail/`** (sauf si `allow_outside_workspace: true`).
- Chaque mission produit un rapport détaillé dans `rapports/` : tout ce qu'il a fait est traçable.
- `max_steps` limite la longueur d'une mission, et donc le coût.
- L'agent a les mêmes droits que ton compte. Pour du 100 % autonome, utilise une machine virtuelle ou un compte dédié.

---

## 6. Architecture (pour faire évoluer le système)

```
agentos/
├── agent.py    → la boucle agentique + le prompt système (la « personnalité »)
├── llm.py      → connecteurs Claude / OpenAI / Ollama / démo
├── tools.py    → les outils (ajoute les tiens ici)
├── memory.py   → mémoire long terme (donnees/memoire.jsonl)
├── daemon.py   → mode système : dossier de missions + planification
├── core.py     → configuration et assemblage
└── __main__.py → ligne de commande
```

**Ajouter un outil** (par ex. envoyer un e-mail) : dans `tools.py`, écris une méthode `t_envoyer_email(self, a, sujet, corps)`, puis ajoute son entrée dans `schemas()`. L'agent saura s'en servir aussitôt.

Outils inclus : `plan`, `update_step`, `run_command`, `read_file`, `write_file`, `edit_file`, `list_dir`, `web_fetch`, `remember`, `recall`, `ask_user`, `delegate` (sous-agent), `finish`.
