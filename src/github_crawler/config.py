import os
import yaml
import json
from typing import Dict, Any

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
