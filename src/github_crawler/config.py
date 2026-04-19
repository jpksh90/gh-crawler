import os
import yaml
import json
from typing import Dict, Any
from InquirerPy import inquirer

def load_yaml_config(file_path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(file_path, "r") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

def save_config(new_config: Dict[str, Any], file_path: str = "config.yaml"):
    # Placeholder for saving configuration
    # In a real application, this would write to a config file like config.yaml
    pass

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
    def __init__(self, args=None):
        self.github_token = (args.github_token if args else None) or os.environ.get("GITHUB_TOKEN")
        self.keywords = (args.keywords if args else None) or os.environ.get("KEYWORDS", "")
        self.language = (args.language if args else None) or os.environ.get("LANGUAGE", "python")
        
        try:
            min_stars_arg = args.min_stars if args else None
            self.min_stars = int(min_stars_arg) if min_stars_arg is not None else int(os.environ.get("MIN_STARS", "100"))
        except (ValueError, TypeError):
            self.min_stars = 100

        try:
            min_forks_arg = args.min_forks if args else None
            self.min_forks = int(min_forks_arg) if min_forks_arg is not None else int(os.environ.get("MIN_FORKS", "0"))
        except (ValueError, TypeError):
            self.min_forks = 0
            
        self.license = (args.license if args else None) or os.environ.get("LICENSE", "")
        
        try:
            limit_arg = args.limit if args else None
            self.limit = int(limit_arg) if limit_arg is not None else int(os.environ.get("LIMIT", "10"))
        except (ValueError, TypeError):
            self.limit = 10

        self.output_dir = os.environ.get("OUTPUT_DIR", "./output")
        self.temp_dir = os.environ.get("TEMP_DIR", "/tmp/gh-crawler")
        self.save_background_report = args.run_background if args else True

        # Ensure dirs exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

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
