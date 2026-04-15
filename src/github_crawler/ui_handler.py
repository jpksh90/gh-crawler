from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.live import Live
from github_crawler.events import EventType, event_bus

console = Console()

class RichUIHandler:
    def __init__(self):
        self.progress = None
        self.active_tasks = {}
        self.status = None
        self._setup_subscriptions()

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
            console.print(Panel(f"[bold green]Synthesized Search Criteria:[/bold green]\n"
                                f"[cyan]Keywords:[/cyan] {data['keywords']}\n"
                                f"[cyan]Language:[/cyan] {data['language']}\n"
                                f"[cyan]Min Stars:[/cyan] {data['min_stars']}\n"
                                f"[cyan]Reasoning:[/cyan] {data.get('reasoning', 'N/A')}"))

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
        repo_name, error = data
        if repo_name in self.active_tasks:
            self.progress.remove_task(self.active_tasks[repo_name])
            del self.active_tasks[repo_name]
        console.print(f"[bold red]✘ Error processing {repo_name}:[/bold red] {error}")

    def on_error(self, message):
        console.print(f"[bold red]ERROR:[/bold red] {message}")

    def on_log(self, message):
        console.print(f"[dim]{message}[/dim]")
