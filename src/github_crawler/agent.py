import os
import subprocess
from rich.console import Console
from rich.panel import Panel

from github_crawler.events import EventType, event_bus

console = Console()

class CodeAgent:
    def __init__(self, repo_name: str, repo_path: str, google_key: str = None, openai_key: str = None):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.google_key = google_key
        self.openai_key = openai_key
        self.trace = []
        self.files_touched = set()
        self.current_task = ""

    def run_session(self, task: str, silent: bool = False):
        self.current_task = task
        self.trace.append({"turn": 1, "thought": "Initial thought process for the task.", "output": "Starting analysis..."})
        event_bus.emit(EventType.LOG, f"{self.repo_name}: agent session started")

        # Placeholder for actual analysis logic
        analysis_result = f"Analysis of '{self.repo_name}' for task: '{task}'. Initial step completed."
        self.trace.append({"turn": 1, "thought": "Completed initial analysis step.", "output": analysis_result})
        event_bus.emit(EventType.LOG, f"{self.repo_name}: agent produced an initial analysis result")

        if not silent:
            console.print(Panel(f"[bold cyan]Agent analyzing:[/bold cyan] {self.repo_name}\nTask: {task}\nResult: {analysis_result}"))
        
        return analysis_result

    def _execute_command(self, command_args, cwd, capture_output=True):
        full_path = os.path.join(self.repo_path, cwd)
        
        self.files_touched.add(cwd) # Track file access
        
        try:
            result = subprocess.run(command_args, cwd=full_path, check=True, capture_output=capture_output, text=True)
            return result.stdout.strip() if capture_output else ""
        except subprocess.CalledProcessError as e:
            return f"Error executing command: {e}"
        except FileNotFoundError:
            return "Command not found. Ensure it's in your PATH."
