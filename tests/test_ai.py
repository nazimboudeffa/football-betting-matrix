"""Tests du contexte d'analyse et du client Ollama local."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from football_betting_matrix import ai
from football_betting_matrix.config import DEFAULT_OLLAMA_URL, ROOT_DIR, Config
from football_betting_matrix.errors import SourceError
from football_betting_matrix.service import DataService
from football_betting_matrix.store import JsonSettingsStore, MemoryCache


class ContextTests(unittest.TestCase):
    def test_normalize_url(self) -> None:
        self.assertEqual(ai.normalize_url(" http://localhost:11434/ "), "http://localhost:11434")
        self.assertEqual(ai.normalize_url(""), DEFAULT_OLLAMA_URL)
        self.assertEqual(ai.normalize_url(None), DEFAULT_OLLAMA_URL)

    def test_build_context_contains_match_model_and_all_strategies(self) -> None:
        payload = {
            "fixture": {
                "id": 12,
                "date": "2026-08-15T20:00:00+02:00",
                "home": {"name": "Lens"},
                "away": {"name": "Lille"},
                "league": {"name": "Ligue 1", "season": 2026, "round": "1"},
                "status": {"label": "A venir"},
                "source": "openfootball",
            },
            "model": {
                "probabilities": {"home": 0.5},
                "scores": [{"score": "1-0", "prob": 0.1}],
                "lambda_home": 1.4,
                "reliability": "bonne",
                "home": {"played": 10},
                "_meta": {"cached": True},
            },
            "selected_strategy": "strict_value",
            "context": {
                "xg": {"home": 1.2, "away": 0.8},
                "stats": {"corners": {"home": 6, "away": 3}},
                "market": {"reference": "pinnacle", "margin": 0.05},
                "referee": {"name": "Duval", "matches": 12},
            },
            "standings": {
                "league": {"id": 140, "name": "Ligue 1", "season": 2026},
                "groups": [
                    {
                        "name": "Classement",
                        "rows": [
                            {
                                "rank": 1,
                                "team": {"id": 1, "name": "Lens"},
                                "points": 42,
                                "form": "VVNVD",
                            }
                        ],
                    }
                ],
                "source": "csv",
                "fetched_at": 1760000000.0,
                "warning": None,
            },
            "strategies": [
                {
                    "id": "poisson",
                    "name": "Poisson",
                    "description": "Sans marge",
                    "rows": [{"label": "Victoire domicile", "prob": 0.5, "odd": 2.0}],
                },
                {
                    "id": "strict_value",
                    "name": "Cote prudente",
                    "description": "Avec marge",
                    "rows": [{"label": "Victoire domicile", "prob": 0.5, "odd": 2.1}],
                },
            ],
        }

        context = ai.build_context(payload)
        data = json.loads(context)

        self.assertEqual(data["match"]["domicile"], "Lens")
        self.assertEqual(data["match"]["competition"], "Ligue 1")
        self.assertEqual(data["modele"]["probabilites"], {"home": 0.5})
        self.assertEqual(data["donnees_match"]["xG"], {"home": 1.2, "away": 0.8})
        self.assertEqual(data["donnees_match"]["marche"]["reference"], "pinnacle")
        self.assertEqual(data["donnees_match"]["arbitre"]["name"], "Duval")
        self.assertEqual(len(data["strategies"]), 2)
        self.assertFalse(data["strategies"][0]["selectionnee"])
        self.assertTrue(data["strategies"][1]["selectionnee"])
        self.assertEqual(data["strategies"][1]["cotes"][0]["odd"], 2.1)
        self.assertEqual(data["classement"]["groups"][0]["rows"][0]["team"]["name"], "Lens")
        self.assertEqual(data["classement"]["league"]["season"], 2026)
        self.assertIn("pas des cotes de bookmaker", data["note"])
        self.assertIn("meme saison que le modele", data["note"])

    def test_build_context_without_standings(self) -> None:
        context = ai.build_context({"fixture": {}, "model": {}})
        self.assertEqual(json.loads(context)["classement"], {})

    def test_build_prompt_uses_default_and_appends_context(self) -> None:
        prompt = ai.build_prompt("  ", "CONTEXTE")
        self.assertTrue(prompt.startswith(ai.DEFAULT_PROMPT))
        self.assertIn("--- DONNEES DE L'ANALYSE ---\nCONTEXTE", prompt)

        custom = ai.build_prompt("Explique brievement", "CONTEXTE")
        self.assertTrue(custom.startswith("Explique brievement"))


class OllamaClientTests(unittest.TestCase):
    def test_list_models_parses_and_sorts_unique_names(self) -> None:
        response = Mock()
        response.json.return_value = {
            "models": [
                {"name": "mistral:latest"},
                {"model": "llama3:8b"},
                {"name": "mistral:latest"},
                {"name": ""},
            ]
        }
        with patch.object(ai.requests, "get", return_value=response) as get:
            models = ai.list_models("http://ollama:11434/")

        self.assertEqual(models, ["llama3:8b", "mistral:latest"])
        get.assert_called_once_with("http://ollama:11434/api/tags", timeout=ai.LIST_TIMEOUT)

    def test_list_models_when_ollama_is_down(self) -> None:
        with patch.object(ai.requests, "get", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(SourceError) as caught:
                ai.list_models()
        self.assertEqual(caught.exception.code, "ollama")
        self.assertIn("ollama serve", str(caught.exception))

    def test_ask_ollama_returns_message_content(self) -> None:
        response = Mock()
        response.json.return_value = {"message": {"content": "Analyse OK"}}
        with patch.object(ai.requests, "post", return_value=response) as post:
            result = ai.ask_ollama("prompt", "mistral", "http://ollama:11434")

        self.assertEqual(result, "Analyse OK")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://ollama:11434/api/chat")
        self.assertEqual(kwargs["json"]["model"], "mistral")
        self.assertEqual(kwargs["json"]["messages"][0]["content"], "prompt")
        self.assertFalse(kwargs["json"]["stream"])

    def test_ask_ollama_rejects_missing_model_and_empty_answer(self) -> None:
        with self.assertRaises(SourceError):
            ai.ask_ollama("prompt", "   ")

        response = Mock()
        response.json.return_value = {"message": {"content": ""}}
        with patch.object(ai.requests, "post", return_value=response):
            with self.assertRaises(SourceError) as caught:
                ai.ask_ollama("prompt", "mistral")
        self.assertIn("vide", str(caught.exception))


class OllamaSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = Config(
            root_dir=ROOT_DIR,
            data_dir=root,
            settings_path=root / "settings.json",
        )
        self.store = JsonSettingsStore(self.config.settings_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_url_and_model_are_persisted(self) -> None:
        service = DataService(self.config, MemoryCache(), self.store)
        self.assertEqual(service.ollama_url(), DEFAULT_OLLAMA_URL)
        self.assertEqual(service.ollama_model(), "")

        service.update_settings({"ollama_url": "http://192.168.1.5:11434/"})
        service.set_ollama_model("mistral:latest")

        reloaded = DataService(self.config, MemoryCache(), JsonSettingsStore(self.config.settings_path))
        self.assertEqual(reloaded.ollama_url(), "http://192.168.1.5:11434")
        self.assertEqual(reloaded.ollama_model(), "mistral:latest")


if __name__ == "__main__":
    unittest.main()
