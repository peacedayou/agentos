import os
"""Tests sans réseau : garde-fous de sécurité, conversion des messages et mode démo."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentos.llm import AnthropicLLM, OpenAICompatLLM
from agentos.memory import Memory
from agentos.tools import Toolbox

ROOT = Path(__file__).resolve().parent.parent


class GardeFous(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ws = Path(self.tmp.name)
        self.tb = Toolbox(str(ws), Memory(str(ws / "m.jsonl")), interactive=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_commande_risquee_refusee(self):
        out, _ = self.tb.call("run_command", {"command": "sudo rm -rf /"})
        self.assertIn("REFUSÉ", out)

    def test_sortie_de_l_espace_de_travail_refusee(self):
        out, err = self.tb.call("read_file", {"path": "../../etc/passwd"})
        self.assertTrue(err)
        self.assertIn("refusé", out.lower())

    def test_lien_symbolique_vers_l_exterieur_refuse(self):
        lien = Path(self.tmp.name) / "fuite"
        os.symlink("/etc", lien)
        out, err = self.tb.call("read_file", {"path": "fuite/hostname"})
        self.assertTrue(err)
        self.assertIn("refusé", out.lower())

    def test_commande_simple(self):
        out, err = self.tb.call("run_command", {"command": "echo ok"})
        self.assertFalse(err)
        self.assertIn("ok", out)

    def test_pas_d_humain_en_mode_autonome(self):
        out, _ = self.tb.call("ask_user", {"question": "?"})
        self.assertIn("Aucun humain", out)


class Conversion(unittest.TestCase):
    msgs = [
        {"role": "user", "text": "salut"},
        {"role": "assistant", "text": "x", "tool_calls": [{"id": "a", "name": "plan", "input": {"steps": []}}]},
        {"role": "tool", "results": [{"id": "a", "name": "plan", "output": "ok", "is_error": False}]},
        {"role": "user", "text": "suite"},
    ]

    def test_anthropic(self):
        c = AnthropicLLM._convert(self.msgs)
        self.assertEqual([m["role"] for m in c], ["user", "assistant", "user"])
        self.assertEqual([b["type"] for b in c[2]["content"]], ["tool_result", "text"])

    def test_openai_compatible(self):
        c = OpenAICompatLLM._convert("sys", self.msgs)
        self.assertEqual([m["role"] for m in c], ["system", "user", "assistant", "tool", "user"])


class Demo(unittest.TestCase):
    def test_mission_en_mode_demo(self):
        r = subprocess.run(
            [sys.executable, "-m", "agentos", "--provider", "mock", "run", "Crée un script de démo et teste-le"],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Mission terminée", r.stdout)


if __name__ == "__main__":
    unittest.main()
