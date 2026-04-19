import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from github_crawler.config import Config, load_yaml_config, save_config


class _PromptResult:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class TestConfigPersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "nested", "config.yaml")
        self.output_dir = os.path.join(self.test_dir, "output")
        self.temp_dir = os.path.join(self.test_dir, "temp")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_save_config_round_trip(self):
        payload = {
            "github_token": "token-123",
            "keywords": "crawler",
            "limit": 7,
        }

        save_config(payload, self.config_path)

        self.assertEqual(load_yaml_config(self.config_path), payload)

    def test_config_reads_saved_values_and_applies_precedence(self):
        save_config(
            {
                "github_token": "saved-token",
                "keywords": "saved keywords",
                "labels": ["android", "nativeactivity"],
                "language": "rust",
                "min_stars": 42,
                "min_forks": 5,
                "license": "mit",
                "limit": 3,
                "output_dir": self.output_dir,
                "temp_dir": self.temp_dir,
                "save_background_report": True,
            },
            self.config_path,
        )

        args = SimpleNamespace(
            github_token=None,
            keywords="cli keywords",
            labels=None,
            language=None,
            min_stars=None,
            min_forks=None,
            license=None,
            limit=None,
            run_background=False,
        )

        with patch.dict(os.environ, {"LANGUAGE": "python"}, clear=True):
            config = Config(args=args, config_file=self.config_path)

        self.assertEqual(config.github_token, "saved-token")
        self.assertEqual(config.keywords, "cli keywords")
        self.assertEqual(config.labels, ["android", "nativeactivity"])
        self.assertEqual(config.language, "python")
        self.assertEqual(config.min_stars, 42)
        self.assertEqual(config.output_dir, self.output_dir)
        self.assertEqual(config.temp_dir, self.temp_dir)
        self.assertFalse(config.save_background_report)

    def test_config_has_no_hardcoded_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config(args=None, config_file=self.config_path)

        self.assertIsNone(config.language)
        self.assertIsNone(config.min_stars)
        self.assertIsNone(config.min_forks)
        self.assertIsNone(config.limit)
        self.assertIsNone(config.output_dir)
        self.assertIsNone(config.temp_dir)

    def test_prompt_for_missing_values_saves_config(self):
        with patch.dict(os.environ, {}, clear=True):
            config = Config(args=None, config_file=self.config_path)

        with patch("github_crawler.config.inquirer.secret", return_value=_PromptResult("prompt-token")), \
             patch("github_crawler.config.inquirer.text", side_effect=[
                 _PromptResult("prompt keywords"),
                 _PromptResult("go"),
                 _PromptResult("android, nativeactivity"),
                 _PromptResult("101"),
                 _PromptResult("12"),
                 _PromptResult("apache-2.0"),
                  _PromptResult("15"),
                  _PromptResult(self.output_dir),
                  _PromptResult(self.temp_dir),
              ]), \
              patch("github_crawler.config.inquirer.confirm", return_value=_PromptResult(True)):
            config.prompt_for_missing_values()

        saved = load_yaml_config(self.config_path)
        self.assertEqual(saved["github_token"], "prompt-token")
        self.assertEqual(saved["keywords"], "prompt keywords")
        self.assertEqual(saved["labels"], ["android", "nativeactivity"])
        self.assertEqual(saved["language"], "go")
        self.assertEqual(saved["min_stars"], 101)
        self.assertEqual(saved["min_forks"], 12)
        self.assertEqual(saved["license"], "apache-2.0")
        self.assertEqual(saved["limit"], 15)
        self.assertEqual(saved["output_dir"], self.output_dir)
        self.assertEqual(saved["temp_dir"], self.temp_dir)
        self.assertTrue(saved["save_background_report"])
        self.assertTrue(os.path.isdir(self.output_dir))
        self.assertTrue(os.path.isdir(self.temp_dir))


if __name__ == "__main__":
    unittest.main()
