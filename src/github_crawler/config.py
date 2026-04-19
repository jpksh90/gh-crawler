import os
import yaml
import json
from typing import Dict, Any, Optional
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

        self.github_token = (getattr(args, "github_token", None) if args else None) or os.environ.get("GITHUB_TOKEN") or saved_config.get("github_token")
        self.keywords = (getattr(args, "keywords", None) if args else None) or os.environ.get("KEYWORDS") or saved_config.get("keywords")
        labels_value = (getattr(args, "labels", None) if args else None) or os.environ.get("LABELS") or saved_config.get("labels")
        self.labels = self._coerce_labels(labels_value)
        self.language = (getattr(args, "language", None) if args else None) or os.environ.get("LANGUAGE") or saved_config.get("language")
        self.min_stars = self._coerce_int(
            getattr(args, "min_stars", None) if args else None,
            os.environ.get("MIN_STARS"),
            saved_config.get("min_stars"),
            field_name="min_stars",
        )
        self.min_forks = self._coerce_int(
            getattr(args, "min_forks", None) if args else None,
            os.environ.get("MIN_FORKS"),
            saved_config.get("min_forks"),
            field_name="min_forks",
        )
        self.license = (getattr(args, "license", None) if args else None) or os.environ.get("LICENSE") or saved_config.get("license")
        self.limit = self._coerce_int(
            getattr(args, "limit", None) if args else None,
            os.environ.get("LIMIT"),
            saved_config.get("limit"),
            field_name="limit",
        )

        self.output_dir = os.environ.get("OUTPUT_DIR") or saved_config.get("output_dir")
        self.temp_dir = os.environ.get("TEMP_DIR") or saved_config.get("temp_dir")
        self.save_background_report = getattr(args, "run_background", None) if args else saved_config.get("save_background_report")

        # Ensure dirs exist
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
        if self.temp_dir:
            os.makedirs(self.temp_dir, exist_ok=True)

    @staticmethod
    def _coerce_int(*candidates, field_name: str) -> Optional[int]:
        for candidate in candidates:
            if candidate in (None, ""):
                continue
            try:
                return int(candidate)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer.") from exc
        return None

    @staticmethod
    def _coerce_labels(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [part.strip() for part in str(value).split(",") if part.strip()]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "github_token": self.github_token,
            "keywords": self.keywords,
            "labels": self.labels,
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
        return bool(self.github_token and self.keywords and self.output_dir and self.temp_dir)

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

        labels_str = inquirer.text(
            message="Labels / Topics (comma-separated):",
            default=", ".join(self.labels)
        ).execute()
        self.labels = self._coerce_labels(labels_str)
        
        # Numeric values
        min_stars_str = inquirer.text(
            message="Minimum Stars:",
            default="" if self.min_stars is None else str(self.min_stars)
        ).execute()
        self.min_stars = None if min_stars_str == "" else int(min_stars_str)

        min_forks_str = inquirer.text(
            message="Minimum Forks:",
            default="" if self.min_forks is None else str(self.min_forks)
        ).execute()
        self.min_forks = None if min_forks_str == "" else int(min_forks_str)

        self.license = inquirer.text(
            message="License (e.g. mit, apache-2.0):",
            default=self.license or ""
        ).execute()

        # Limits and Output
        limit_str = inquirer.text(
            message="Maximum repositories to process (leave blank for no limit):",
            default="" if self.limit is None else str(self.limit)
        ).execute()
        self.limit = None if limit_str == "" else int(limit_str)

        self.output_dir = inquirer.text(
            message="Output Directory:",
            default=self.output_dir or ""
        ).execute()

        self.temp_dir = inquirer.text(
            message="Temporary Directory:",
            default=self.temp_dir or ""
        ).execute()
        
        self.save_background_report = inquirer.confirm(
            message="Save background report?",
            default=bool(self.save_background_report)
        ).execute()

        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
        if self.temp_dir:
            os.makedirs(self.temp_dir, exist_ok=True)
        self.save()
