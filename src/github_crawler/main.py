import os
import time
from datetime import datetime

from github import GithubException, RateLimitExceededException, UnknownObjectException, BadCredentialsException
from rich.console import Console

from github_crawler.events import EventType, event_bus
from github_crawler.reporting import generate_markdown_report, display_results_table, save_background_report
from github_crawler.search import GitHubSearcher, SearchSynthesizer
from github_crawler.config import Config
from github_crawler.ui_handler import RichUIHandler
from github_crawler.cli import parse_args, explore_repo_files
from github_crawler.source_scan import SourcePropertyScanner
from github_crawler.github_utils import clone_repo, count_lines_of_code
from github_crawler.session_store import create_session, delete_session, list_sessions, update_session_metadata
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from rich.table import Table

console = Console()

MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

def synthesize_scan_spec(config: Config, task: str):
    synthesizer = SearchSynthesizer(
        google_key=os.environ.get("GOOGLE_API_KEY"),
        openai_key=os.environ.get("OPENAI_API_KEY"),
    )
    event_bus.emit(EventType.SYNTHESIS_STARTED)
    synthesis_data = synthesizer.synthesize(config.keywords)
    search_spec = {
        "repository_request": config.keywords,
        "keywords": synthesis_data["keywords"],
        "labels": synthesis_data.get("labels", []),
        "language": synthesis_data.get("language", config.language),
        "min_stars": synthesis_data.get("min_stars")
        if synthesis_data.get("min_stars") is not None
        else config.min_stars,
        "min_forks": synthesis_data.get("min_forks")
        if synthesis_data.get("min_forks") is not None
        else config.min_forks,
        "license": synthesis_data.get("license") or config.license,
        "reasoning": synthesis_data.get("reasoning", ""),
        "property_query": task,
    }
    event_bus.emit(EventType.SYNTHESIS_FINISHED, search_spec)
    return search_spec


def build_prompted_search_spec(config: Config, task: str):
    return {
        "repository_request": config.keywords,
        "keywords": config.keywords,
        "labels": list(config.labels),
        "language": config.language,
        "min_stars": config.min_stars,
        "min_forks": config.min_forks,
        "license": config.license,
        "reasoning": "Using search criteria entered directly in the terminal interface.",
        "property_query": task,
    }


def resolve_task(task: str | None) -> str:
    if task and task.strip():
        return task.strip()
    return inquirer.text(
        message="Source Property Request:",
        default="",
    ).execute().strip()


def search_repositories(config: Config, search_spec):
    """
    Searches for repositories based on the provided configuration.
    Emits search events and returns a list of repository objects.
    """
    searcher = GitHubSearcher(config.github_token)
    event_bus.emit(EventType.SEARCH_STARTED)
    
    for attempt in range(MAX_RETRIES):
        try:
            repos = searcher.search_repositories(
                keywords=search_spec["keywords"],
                labels=search_spec.get("labels"),
                language=search_spec["language"],
                min_stars=search_spec["min_stars"],
                min_forks=search_spec["min_forks"],
                license=search_spec["license"],
                limit=config.limit
            )
            event_bus.emit(EventType.SEARCH_SUCCESS, len(repos))
            return repos
        except RateLimitExceededException as e:
            # Specific handling for rate limit exceeded
            event_bus.emit(EventType.LOG, f"Rate limit exceeded. Headers: {e.headers}")
            if attempt < MAX_RETRIES - 1:
                wait_time = int(e.headers.get("X-RateLimit-Reset", RETRY_DELAY)) + 1
                event_bus.emit(EventType.LOG, f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                # Emit structured error for RateLimitExceededException
                event_bus.emit(EventType.REPO_ERROR, (None, { # None for repo_name as it's a global search error
                    "status": e.status,
                    "data": e.data,
                    "headers": e.headers,
                    "message": f"Rate limit exceeded after {MAX_RETRIES} retries."
                }))
                event_bus.emit(EventType.ERROR, "API rate limit exceeded. Please check your token and try again later.")
                return []
        except GithubException as e:
            # General GithubException handling with structured data
            error_details = {
                "status": e.status,
                "data": e.data,
                "headers": e.headers,
                "message": str(e)
            }
            event_bus.emit(EventType.REPO_ERROR, (None, error_details)) # None for repo_name as it's a global search error
            event_bus.emit(EventType.ERROR, f"GitHub API error during search: {e.message}. Status: {e.status}")
            return [] # Abort search on other GitHub API errors
        except Exception as e:
            # Handle unexpected errors during search
            event_bus.emit(EventType.REPO_ERROR, (None, str(e))) # None for repo_name as it's a global search error
            event_bus.emit(EventType.ERROR, f"An unexpected error occurred during repository search: {e}")
            return []
            
    # If all retries fail for rate limit
    return []


def process_repository(repo, session, task: str):
    """
    Processes a single repository: clones, analyzes, and reports.
    Emits repo-specific events.
    """
    repo_name = repo.full_name
    clone_dir = session.repo_clone_dir(repo_name)
    event_bus.emit(EventType.REPO_START, repo_name)

    try:
        # Use shared utility for cloning to keep clone behavior centralized.
        event_bus.emit(EventType.LOG, f"{repo_name}: cloning repository")
        clone_repo(repo.clone_url, clone_dir)
        event_bus.emit(EventType.LOG, f"{repo_name}: clone complete")

        event_bus.emit(EventType.LOG, f"{repo_name}: scanning source properties")
        scanner = SourcePropertyScanner(repo_name=repo_name, repo_path=clone_dir)
        analysis_result = scanner.scan(task)
        event_bus.emit(EventType.LOG, f"{repo_name}: source scan complete")

        # Count lines with the shared pygount-backed utility.
        event_bus.emit(EventType.LOG, f"{repo_name}: counting lines of code")
        lines_of_code = count_lines_of_code(clone_dir)
        event_bus.emit(EventType.LOG, f"{repo_name}: counted {lines_of_code:,} lines of code")

        result = {
            "name": repo_name,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "lines_of_code": lines_of_code,
            "analysis": analysis_result["summary"],
            "trace": analysis_result["trace"],
            "files_touched": analysis_result["files_touched"],
            "property_matches": analysis_result["findings"],
            "clone_path": clone_dir,
        }

        event_bus.emit(EventType.REPO_SUCCESS, repo_name)
        return result

    except UnknownObjectException:
        # Handle cases where repo is not found (e.g., deleted or private)
        error_details = {
            "status": 404,
            "message": "Repository not found or access denied."
        }
        event_bus.emit(EventType.REPO_ERROR, (repo_name, error_details))
        return None
    except BadCredentialsException as e:
        # Handle authentication errors specifically
        error_details = {
            "status": e.status,
            "data": e.data,
            "headers": e.headers,
            "message": str(e)
        }
        event_bus.emit(EventType.REPO_ERROR, (repo_name, error_details))
        event_bus.emit(EventType.ERROR, "Authentication failed. Please check your GitHub token.")
        return None
    except GithubException as e:
        # Handle other GitHub API errors with structured data
        error_details = {
            "status": e.status,
            "data": e.data,
            "headers": e.headers,
            "message": str(e)
        }
        event_bus.emit(EventType.REPO_ERROR, (repo_name, error_details))
        return None
    except Exception as e:
        # Handle any other unexpected errors during repository processing
        event_bus.emit(EventType.REPO_ERROR, (repo_name, str(e)))
        return None


def save_scan_outputs(all_results, config: Config, task: str, session, save_reports: bool = True):
    artifacts = {
        "session_id": session.session_id,
        "session_dir": session.session_dir,
    }
    if not save_reports or not all_results:
        return artifacts

    markdown_report = generate_markdown_report(all_results, task)
    report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_filepath = os.path.join(session.artifact_dir, report_filename)
    try:
        with open(report_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        artifacts["markdown_report"] = report_filepath
        event_bus.emit(EventType.LOG, f"Markdown report saved to: {report_filepath}")
    except Exception as e:
        event_bus.emit(EventType.ERROR, f"Error saving markdown report: {e}")

    if config.save_background_report:
        background_report_filename = f"background_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        background_report_filepath = os.path.join(session.artifact_dir, background_report_filename)
        if save_background_report(all_results, task, background_report_filepath):
            artifacts["background_report"] = background_report_filepath
            event_bus.emit(EventType.LOG, f"Background scan report saved to: {background_report_filepath}")
        else:
            event_bus.emit(EventType.ERROR, "Error saving background scan report.")

    return artifacts


def run_interactive_exploration(all_results):
    while True:
        choices = [Choice(res['name'], name=res['name']) for res in all_results]
        choices.append(Choice(value="quit", name="[Quit]"))

        selected_repo_name = inquirer.select(
            message="Select a repository to explore interactively:",
            choices=choices
        ).execute()

        if selected_repo_name == "quit":
            break

        selected_result = next(result for result in all_results if result["name"] == selected_repo_name)
        explore_repo_files(selected_result["clone_path"])


def run_crawler(config: Config, task: str, interactive: bool = False,
                render_console: bool = True, save_reports: bool = True, use_synthesis: bool = True):
    if not config.github_token:
        event_bus.emit(EventType.ERROR, "GitHub token not found. Please set it in config or environment.")
        return [], {}
    if not config.keywords:
        event_bus.emit(EventType.ERROR, "Repository request not found. Please provide search keywords.")
        return [], {}
    if not config.output_dir or not config.temp_dir:
        event_bus.emit(EventType.ERROR, "Output and temporary directories must be provided explicitly.")
        return [], {}
    if not task.strip():
        event_bus.emit(EventType.ERROR, "Source property request must be provided explicitly.")
        return [], {}

    session = create_session(config.output_dir, config.keywords, task)
    event_bus.emit(EventType.LOG, f"Session workspace created at {session.session_dir}")
    search_spec = synthesize_scan_spec(config, task) if use_synthesis else build_prompted_search_spec(config, task)
    update_session_metadata(
        session,
        {
            "status": "running",
            "search_spec": search_spec,
        },
    )

    # Search for repositories
    repos_to_process = search_repositories(config, search_spec)

    if not repos_to_process:
        no_results_message = "No repositories found matching the criteria."
        update_session_metadata(session, {"status": "empty"})
        if render_console:
            console.print(f"[yellow]{no_results_message}[/yellow]")
        else:
            event_bus.emit(EventType.LOG, no_results_message)
        return [], {"session_id": session.session_id, "session_dir": session.session_dir}

    event_bus.emit(EventType.PROCESSING_STARTED)
    all_results = []
    event_bus.emit(EventType.LOG, f"Preparing to process {len(repos_to_process)} repositories")

    for repo in repos_to_process:
        result = process_repository(repo, session, task)
        if result:
            all_results.append(result)

    event_bus.emit(EventType.PROCESSING_FINISHED)

    if render_console and all_results:
        display_results_table(all_results)

    artifacts = save_scan_outputs(all_results, config, task, session, save_reports=save_reports)
    update_session_metadata(
        session,
        {
            "status": "complete",
            "repositories": [
                {
                    "name": result["name"],
                    "url": result["url"],
                    "clone_path": result["clone_path"],
                    "matches": len(result.get("property_matches", [])),
                }
                for result in all_results
            ],
            "artifacts": artifacts,
            "result_count": len(all_results),
        },
    )

    if interactive and all_results:
        run_interactive_exploration(all_results)

    return all_results, artifacts


def print_sessions(output_dir: str):
    sessions = list_sessions(output_dir)
    if not sessions:
        console.print("[yellow]No persisted sessions found.[/yellow]")
        return

    table = Table(title="Persisted Sessions", show_header=True, header_style="bold cyan")
    table.add_column("Session ID")
    table.add_column("Status")
    table.add_column("Repositories", justify="right")
    table.add_column("Created")
    table.add_column("Request")
    for session in sessions:
        table.add_row(
            session.get("session_id", ""),
            session.get("status", ""),
            str(session.get("result_count", 0)),
            session.get("created_at", ""),
            session.get("repository_request", ""),
        )
    console.print(table)


def delete_session_with_prompt(output_dir: str, session_id: str):
    persist_archive = inquirer.confirm(
        message="Persist this session as a zip archive before deleting it?",
        default=True,
    ).execute()
    archive_path = delete_session(output_dir, session_id, persist_archive=persist_archive)
    if archive_path:
        console.print(f"[green]Deleted session {session_id} and archived it to {archive_path}[/green]")
        return
    console.print(f"[green]Deleted session {session_id}[/green]")


def run_gui_mode():
    from github_crawler.gui import launch_gui

    launch_gui()


def main(argv=None):
    """Main function to orchestrate the GitHub crawler."""
    args = parse_args(argv)
    if args.gui:
        run_gui_mode()
        return

    RichUIHandler() # Initialize UI Handler

    config = Config(args)

    if args.list_sessions:
        if not config.output_dir:
            console.print("[red]Output directory must be configured to list sessions.[/red]")
            return
        print_sessions(config.output_dir)
        return

    if args.delete_session:
        if not config.output_dir:
            console.print("[red]Output directory must be configured to delete sessions.[/red]")
            return
        delete_session_with_prompt(config.output_dir, args.delete_session)
        return

    config.prompt_for_missing_values()

    task = resolve_task(args.task)
    if not task:
        console.print("[red]Source property request is required.[/red]")
        return

    run_crawler(
        config=config,
        task=task,
        interactive=args.interactive,
        render_console=True,
        save_reports=True,
        use_synthesis=False,
    )


if __name__ == "__main__":
    # This is a simplified entry point. In a real CLI, this would be handled by cli.py
    # For demonstration, we'll directly call main()
    main()
