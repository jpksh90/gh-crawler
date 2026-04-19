from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from github_crawler.events import EventType, event_bus
import os
from datetime import datetime
import json # Import json for handling dictionary data

console = Console()

# Define the path for the error log file
ERROR_LOG_DIR = "/Users/jyp/.gemini/tmp/crawler"
ERROR_LOG_FILE = os.path.join(ERROR_LOG_DIR, "error.log")

class RichUIHandler:
    def __init__(self):
        self.progress = None
        self.active_tasks = {}
        self.status = None
        self._setup_subscriptions()
        self._ensure_log_dir_exists()

    def _ensure_log_dir_exists(self):
        if not os.path.exists(ERROR_LOG_DIR):
            os.makedirs(ERROR_LOG_DIR)

    def _log_error_to_file(self, message, repo_name=None, error_details=None):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] "
        if repo_name:
            log_entry += f"Repository: {repo_name} | "
        
        if isinstance(error_details, dict):
            # Log structured error details
            status = error_details.get("status")
            data = error_details.get("data")
            headers = error_details.get("headers")
            error_msg = error_details.get("message", message) # Use message from dict if available

            log_entry += f"Message: {error_msg} | "
            if status:
                log_entry += f"Status: {status} | "
            if data:
                # Pretty print JSON data if it's a dict, otherwise just convert to string
                try:
                    # Ensure data is serializable, especially if it contains complex objects
                    data_str = json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data)
                except TypeError:
                    data_str = str(data) # Fallback for non-serializable types
                log_entry += f"Data: {data_str} | "
            if headers:
                # Headers are usually dicts, JSON dump is good
                try:
                    headers_str = json.dumps(headers)
                except TypeError:
                    headers_str = str(headers)
                log_entry += f"Headers: {headers_str} | "
        else:
            # Log plain string message
            log_entry += f"Message: {error_details} | "
        
        # Append the primary message if it wasn't fully covered by error_details
        if not isinstance(error_details, dict) or not error_details.get("message"):
             log_entry += f"Message: {message} | "

        log_entry += "\n" # Ensure a newline at the end of each log entry

        try:
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            console.print(f"[bold red]Failed to write to error log file {ERROR_LOG_FILE}:[/bold red] {e}")

    def _setup_subscriptions(self):
        event_bus.subscribe(EventType.SYNTHESIS_STARTED, self.on_synthesis_started)
        event_bus.subscribe(EventType.SYNTHESIS_FINISHED, self.on_synthesis_finished)
        event_bus.subscribe(EventType.SEARCH_STARTED, self.on_search_started)
        event_bus.subscribe(EventType.SEARCH_SUCCESS, self.on_search_success)
        event_bus.subscribe(EventType.PROCESSING_STARTED, self.on_processing_started)
        event_bus.subscribe(EventType.PROCESSING_FINISHED, self.on_processing_finished)
        event_bus.subscribe(EventType.REPO_START, self.on_repo_start)
        event_bus.subscribe(EventType.REPO_SUCCESS, self.on_repo_success)
        event_bus.subscribe(EventType.REPO_ERROR, self.on_repo_error)
        event_bus.subscribe(EventType.ERROR, self.on_error)
        event_bus.subscribe(EventType.LOG, self.on_log)

    def on_synthesis_started(self, _):
        self.status = console.status("[bold cyan]Synthesizing search patterns...[/bold cyan]")
        self.status.start()

    def on_synthesis_finished(self, data):
        if self.status:
            self.status.stop()
        if data:
            # Corrected multi-line f-string formatting for Panel
            panel_content = (
                f"[bold green]Synthesized Search Criteria:[/bold green]\n"
                f"[cyan]Keywords:[/cyan] {data['keywords']}\n"
                f"[cyan]Language:[/cyan] {data['language']}\n"
                f"[cyan]Min Stars:[/cyan] {data['min_stars']}\n"
                f"[cyan]Reasoning:[/cyan] {data.get('reasoning', 'N/A')}"
            )
            console.print(Panel(panel_content))

    def on_search_started(self, _):
        console.print("[cyan]Attempting to acquire token and search GitHub...[/cyan]")

    def on_search_success(self, count):
        console.print(f"[green]Successfully retrieved {count} repositories.[/green]")

    def on_processing_started(self, _):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        )
        self.progress.start()

    def on_processing_finished(self, _):
        if self.progress:
            self.progress.stop()

    def on_repo_start(self, repo_name):
        if self.progress:
            task_id = self.progress.add_task(description=f"Analyzing {repo_name}...", total=None)
            self.active_tasks[repo_name] = task_id

    def on_repo_success(self, repo_name):
        if repo_name in self.active_tasks:
            self.progress.remove_task(self.active_tasks[repo_name])
            del self.active_tasks[repo_name]
        console.print(f"[green]✔[/green] Finished analysis of {repo_name}")

    def on_repo_error(self, data):
        repo_name, error_details = data
        
        # Log the error to file, passing the structured error_details if available
        self._log_error_to_file(message="Error processing repository", repo_name=repo_name, error_details=error_details)
        
        if repo_name in self.active_tasks:
            self.progress.remove_task(self.active_tasks[repo_name])
            del self.active_tasks[repo_name]
        
        # Display error to console, trying to be informative
        if isinstance(error_details, dict):
            console.print(f"[bold red]✘ Error processing {repo_name}:[/bold red] Status {error_details.get('status', 'N/A')}, Message: {error_details.get('message', str(error_details))}")
        else:
            console.print(f"[bold red]✘ Error processing {repo_name}:[/bold red] {error_details}")

    def on_error(self, message):
        # Log the error to file
        self._log_error_to_file(message=message)
        console.print(f"[bold red]ERROR:[/bold red] {message}")

    def on_log(self, message):
        console.print(f"[dim]{message}[/dim]")
