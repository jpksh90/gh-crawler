import unittest
import os
import shutil
import tempfile
from unittest.mock import patch

from github_crawler.cli import parse_args
from github_crawler.config import Config, load_yaml_config
from github_crawler.events import EventType, event_bus
from github_crawler.gui import BrowserGuiApp
from github_crawler.main import main


class TestGuiMode(unittest.TestCase):
	def setUp(self):
		self.test_dir = tempfile.mkdtemp()
		self.config_path = os.path.join(self.test_dir, "gui-config.yaml")
		self.output_dir = os.path.join(self.test_dir, "output")
		self.temp_dir = os.path.join(self.test_dir, "temp")

	def tearDown(self):
		shutil.rmtree(self.test_dir)

	def test_parse_args_accepts_gui_flag(self):
		args = parse_args(["-g"])

		self.assertTrue(args.gui)

	def test_main_routes_to_gui_mode(self):
		with patch("github_crawler.main.run_gui_mode") as run_gui_mode:
			main(["-g"])

		run_gui_mode.assert_called_once_with()

	def test_browser_gui_save_config_persists_values(self):
		app = BrowserGuiApp()
		app.base_config = Config(args=None, config_file=self.config_path)

		payload = {
			"github_token": "token-123",
			"keywords": "graph crawler",
			"language": "python",
			"license": "mit",
			"min_stars": "15",
			"min_forks": "2",
			"limit": "8",
			"save_background_report": True,
			"task": "Analyze dependency graph",
			"output_dir": self.output_dir,
			"temp_dir": self.temp_dir,
		}

		result = app.save_config(payload)

		saved = load_yaml_config(self.config_path)
		self.assertIn("Configuration saved", result["message"])
		self.assertEqual(saved["github_token"], "token-123")
		self.assertEqual(saved["keywords"], "graph crawler")
		self.assertEqual(saved["output_dir"], self.output_dir)
		self.assertEqual(saved["temp_dir"], self.temp_dir)

	def test_browser_gui_start_scan_uses_run_crawler_results(self):
		app = BrowserGuiApp()
		app.base_config = Config(args=None, config_file=self.config_path)
		artifact_path = os.path.join(self.test_dir, "report.md")
		with open(artifact_path, "w", encoding="utf-8") as handle:
			handle.write("report")

		payload = {
			"github_token": "token-123",
			"keywords": "graph crawler",
			"language": "python",
			"license": "mit",
			"min_stars": "15",
			"min_forks": "2",
			"limit": "8",
			"save_background_report": "true",
			"task": "Analyze dependency graph",
			"output_dir": self.output_dir,
			"temp_dir": self.temp_dir,
		}

		class ImmediateThread:
			def __init__(self, target=None, args=None, daemon=None):
				self.target = target
				self.args = args or ()

			def start(self):
				if self.target:
					self.target(*self.args)

		with patch("github_crawler.gui.threading.Thread", ImmediateThread), \
			 patch("github_crawler.gui.run_crawler", return_value=(
				 [{
					"name": "owner/repo",
					"url": "https://example.com/repo",
					"stars": 42,
					"language": "Python",
					"lines_of_code": 123,
					"analysis": "Looks good.",
					"trace": [],
					"files_touched": [],
				 }],
				 {"markdown_report": artifact_path}
			 )):
			response = app.start_scan(payload)

		state = app.snapshot()
		self.assertEqual(response["message"], "Scan started.")
		self.assertFalse(state["running"])
		self.assertEqual(len(state["results"]), 1)
		self.assertTrue(state["artifacts"]["markdown_report"])
		self.assertIn("Completed: 1 repositories", state["status"])
		self.assertEqual(state["progress"]["phase"], "complete")
		self.assertEqual(state["progress"]["completed_repos"], 0)

	def test_browser_gui_snapshot_contains_intermediate_messages(self):
		app = BrowserGuiApp()
		app.base_config = Config(args=None, config_file=self.config_path)
		artifact_path = os.path.join(self.test_dir, "report.md")
		with open(artifact_path, "w", encoding="utf-8") as handle:
			handle.write("report")

		payload = {
			"github_token": "token-123",
			"keywords": "graph crawler",
			"language": "python",
			"license": "mit",
			"min_stars": "15",
			"min_forks": "2",
			"limit": "8",
			"save_background_report": True,
			"task": "Analyze dependency graph",
			"output_dir": self.output_dir,
			"temp_dir": self.temp_dir,
		}

		class ImmediateThread:
			def __init__(self, target=None, args=None, daemon=None):
				self.target = target
				self.args = args or ()

			def start(self):
				if self.target:
					self.target(*self.args)

		def fake_run_crawler(*_args, **_kwargs):
			event_bus.emit(EventType.SEARCH_SUCCESS, 1)
			event_bus.emit(EventType.PROCESSING_STARTED)
			event_bus.emit(EventType.REPO_START, "owner/repo")
			event_bus.emit(EventType.LOG, "owner/repo: cloning repository")
			event_bus.emit(EventType.LOG, "owner/repo: starting analysis")
			event_bus.emit(EventType.REPO_SUCCESS, "owner/repo")
			event_bus.emit(EventType.PROCESSING_FINISHED)
			return ([{
				"name": "owner/repo",
				"url": "https://example.com/repo",
				"stars": 42,
				"language": "Python",
				"lines_of_code": 123,
				"analysis": "Looks good.",
				"trace": [],
				"files_touched": [],
			}], {"markdown_report": artifact_path})

		with patch("github_crawler.gui.threading.Thread", ImmediateThread), \
			 patch("github_crawler.gui.run_crawler", side_effect=fake_run_crawler):
			app.start_scan(payload)

		state = app.snapshot()
		joined_logs = "\n".join(state["logs"])
		self.assertIn("owner/repo: cloning repository", joined_logs)
		self.assertIn("owner/repo: starting analysis", joined_logs)
		self.assertEqual(state["progress"]["total_repos"], 1)
		self.assertEqual(state["progress"]["completed_repos"], 1)
		self.assertEqual(state["progress"]["phase"], "complete")
		self.assertEqual(state["progress"]["current_repo"], None)


if __name__ == "__main__":
	unittest.main()

