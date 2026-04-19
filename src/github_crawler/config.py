import os
import yaml
import json
from typing import Dict, Any
from InquirerPy import inquirer

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.gh-crawler.yaml")

def load_yaml_config(file_path: str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    try:
        with open(os.path.expanduser(file_path), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return {}

def save_config(new_config: Dict[str, Any], file_path: str = DEFAULT_CONFIG_PATH):
    """Persist configuration as YAML, creating parent directories when needed."""
    resolved_path = os.path.expanduser(file_path)
    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    temp_path = f"{resolved_path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(new_config, f, default_flow_style=False, sort_keys=True, allow_unicode=True)
        os.replace(temp_path, resolved_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

def load_project_memory(memory_file: str = ".gemini_project_memory.json") -> Dict[str, Any]:
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_project_memory(data: Dict[str, Any], memory_file: str = ".gemini_project_memory.json"):
    try:
        with open(memory_file, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

class Config:
    def __init__(self, args=None, config_file: str = DEFAULT_CONFIG_PATH):
        self.config_file = os.path.expanduser(config_file)
        saved_config = load_yaml_config(self.config_file)

        self.github_token = (args.github_token if args else None) or os.environ.get("GITHUB_TOKEN") or saved_config.get("github_token")
        self.keywords = (args.keywords if args else None) or os.environ.get("KEYWORDS") or saved_config.get("keywords", "")
        self.language = (args.language if args else None) or os.environ.get("LANGUAGE") or saved_config.get("language", "python")

        try:
            min_stars_arg = args.min_stars if args else None
            min_stars_value = min_stars_arg if min_stars_arg is not None else os.environ.get("MIN_STARS", saved_config.get("min_stars", 100))
            self.min_stars = int(min_stars_value)
        except (ValueError, TypeError):
            self.min_stars = 100

        try:
            min_forks_arg = args.min_forks if args else None
            min_forks_value = min_forks_arg if min_forks_arg is not None else os.environ.get("MIN_FORKS", saved_config.get("min_forks", 0))
            self.min_forks = int(min_forks_value)
        except (ValueError, TypeError):
            self.min_forks = 0
            
        self.license = (args.license if args else None) or os.environ.get("LICENSE") or saved_config.get("license", "")

        try:
            limit_arg = args.limit if args else None
            limit_value = limit_arg if limit_arg is not None else os.environ.get("LIMIT", saved_config.get("limit", 10))
            self.limit = int(limit_value)
        except (ValueError, TypeError):
            self.limit = 10

        self.output_dir = os.environ.get("OUTPUT_DIR") or saved_config.get("output_dir", "./output")
        self.temp_dir = os.environ.get("TEMP_DIR") or saved_config.get("temp_dir", "/tmp/gh-crawler")
        self.save_background_report = args.run_background if args else saved_config.get("save_background_report", True)

        # Ensure dirs exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "github_token": self.github_token,
            "keywords": self.keywords,
            "language": self.language,
            "min_stars": self.min_stars,
            "min_forks": self.min_forks,
            "license": self.license,
            "limit": self.limit,
            "output_dir": self.output_dir,
            "temp_dir": self.temp_dir,
            "save_background_report": self.save_background_report,
        }

    def save(self):
        save_config(self.to_dict(), self.config_file)

    def is_complete(self) -> bool:
        return bool(self.github_token and self.keywords)

    def prompt_for_missing_values(self):
        # GitHub Token
        self.github_token = inquirer.secret(
            message="GitHub API Token:",
            default=self.github_token or ""
        ).execute()
        
        # Search Criteria
        self.keywords = inquirer.text(
            message="Search Keywords:",
            default=self.keywords or ""
        ).execute()
        
        self.language = inquirer.text(
            message="Programming Language (leave blank for all):",
            default=self.language or ""
        ).execute()
        
        # Numeric values
        min_stars_str = inquirer.text(
            message="Minimum Stars:",
            default=str(self.min_stars)
        ).execute()
        try:
            self.min_stars = int(min_stars_str)
        except ValueError:
            self.min_stars = 100

        min_forks_str = inquirer.text(
            message="Minimum Forks:",
            default=str(self.min_forks)
        ).execute()
        try:
            self.min_forks = int(min_forks_str)
        except ValueError:
            self.min_forks = 0

        self.license = inquirer.text(
            message="License (e.g. mit, apache-2.0):",
            default=self.license or ""
        ).execute()

        # Limits and Output
        limit_str = inquirer.text(
            message="Maximum repositories to process:",
            default=str(self.limit)
        ).execute()
        try:
            self.limit = int(limit_str)
        except ValueError:
            self.limit = 10

        self.output_dir = inquirer.text(
            message="Output Directory:",
            default=self.output_dir
        ).execute()
        
        self.save_background_report = inquirer.confirm(
            message="Save background report?",
            default=self.save_background_report
        ).execute()

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        self.save()

