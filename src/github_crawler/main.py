import os
import shutil
import time
import subprocess
from datetime import datetime

from github import GithubException, RateLimitExceededException, UnknownObjectException, BadCredentialsException
from rich.console import Console

from github_crawler.events import EventType, event_bus
from github_crawler.reporting import generate_markdown_report, display_results_table, save_background_report
from github_crawler.search import GitHubSearcher
from github_crawler.config import Config
from github_crawler.ui_handler import RichUIHandler
from github_crawler.cli import parse_args, explore_repo_files
from github_crawler.agent import CodeAgent
from InquirerPy import inquirer
from InquirerPy.base.control import Choice

console = Console()

MAX_RETRIES = 3
RETRY_DELAY = 5 # seconds

def search_repositories(config: Config):
    """
    Searches for repositories based on the provided configuration.
    Emits search events and returns a list of repository objects.
    """
    searcher = GitHubSearcher(config.github_token)
    event_bus.emit(EventType.SEARCH_STARTED)
    
    for attempt in range(MAX_RETRIES):
        try:
            repos = searcher.search_repositories(
                keywords=config.keywords,
                language=config.language,
                min_stars=config.min_stars,
                min_forks=config.min_forks,
                license=config.license,
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


def process_repository(repo, config: Config, temp_dir: str, task: str = "Analyze repository structure"):
    """
    Processes a single repository: clones, analyzes, and reports.
    Emits repo-specific events.
    """
    repo_name = repo.full_name
    event_bus.emit(EventType.REPO_START, repo_name)

    try:
        # Clone repository
        shutil.rmtree(temp_dir, ignore_errors=True) # Clean up previous clone
        os.makedirs(temp_dir, exist_ok=True)
        
        # Use git command for cloning
        repo_url = repo.clone_url
        subprocess.run(["git", "clone", "--depth", "1", repo_url, temp_dir], check=True, capture_output=True)

        # Use CodeAgent for analysis
        agent = CodeAgent(
            repo_name=repo_name, 
            repo_path=temp_dir, 
            google_key=os.environ.get("GOOGLE_API_KEY"), 
            openai_key=os.environ.get("OPENAI_API_KEY")
        )
        
        analysis = agent.run_session(task=task, silent=True)
        trace = agent.trace
        files_touched = list(agent.files_touched)

        # Also count lines of code as a fallback/extra metric
        lines_of_code = 0
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines_of_code += len(f.readlines())
                        rel_path = os.path.relpath(file_path, temp_dir)
                        if rel_path not in files_touched:
                            files_touched.append(rel_path)
                    except Exception:
                        pass

        result = {
            "name": repo_name,
            "url": repo.html_url,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "lines_of_code": lines_of_code,
            "analysis": analysis,
            "trace": trace,
            "files_touched": files_touched
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
    finally:
        # Clean up cloned repo
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    """Main function to orchestrate the GitHub crawler."""
    args = parse_args()
    RichUIHandler() # Initialize UI Handler

    config = Config(args)
    
    # If config is not fully set, prompt user
    if not config.is_complete():
        config.prompt_for_missing_values()
        
    # Ensure GitHub token is set
    if not config.github_token:
        console.print("[bold red]Error:[/bold red] GitHub token not found. Please set it in config or environment.")
        return

    event_bus.emit(EventType.SYNTHESIS_STARTED)
    # Placeholder for synthesis logic
    synthesis_data = {
        "keywords": config.keywords,
        "language": config.language,
        "min_stars": config.min_stars,
        "reasoning": "Searching for popular Python repositories based on keywords."
    }
    event_bus.emit(EventType.SYNTHESIS_FINISHED, synthesis_data)

    # Search for repositories
    repos_to_process = search_repositories(config)

    # Check if search returned any repos and handle no-results/errors from search
    if not repos_to_process:
        # If search_repositories returned an empty list, it might have already emitted
        # an error event (e.g., rate limit, API error). If not, we can emit a generic
        # message indicating no results or search failure.
        # This logic assumes that if repos_to_process is empty, it's either due to
        # an error already handled or genuinely no results found.
        # We avoid double-emitting errors here.
        # The check `any(e['type'] == EventType.ERROR for e in ui_handler._event_log if e['data'])`
        # is a simplification and might not be robust as _event_log might not be accessible or populated.
        # A more reliable approach would be to have search_repositories return a status flag or
        # ensure errors are always emitted.
        # For now, we'll rely on the fact that if search_repositories failed, it likely emitted an error.
        # If it simply found no results, no specific error needs to be printed here.
        pass # Rely on search_repositories to emit errors if it fails.


    # Processing Repositories
    if repos_to_process: # Only proceed if we have repositories to process
        event_bus.emit(EventType.PROCESSING_STARTED)
        all_results = []
        errors_encountered = [] # This list seems to be for capturing string error messages
        
        # Use a temporary directory for cloning each repo
        temp_repo_dir = os.path.join(config.temp_dir, "repo_clone") 
        task = args.task or "Analyze repository structure"

        for repo in repos_to_process:
            result = process_repository(repo, config, temp_repo_dir, task)
            if result:
                all_results.append(result)
            else:
                # process_repository already emits structured errors via event_bus.
                # This 'errors_encountered' list might be for capturing string errors
                # from general Exceptions caught in process_repository, if any.
                pass 
        
        event_bus.emit(EventType.PROCESSING_FINISHED)

        # Reporting
        if all_results:
            display_results_table(all_results)
            markdown_report = generate_markdown_report(all_results, "Global Search")
            
            # Save markdown report to a file
            report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            report_filepath = os.path.join(config.output_dir, report_filename)
            try:
                with open(report_filepath, "w", encoding="utf-8") as f:
                    f.write(markdown_report)
                console.print(f"[green]Markdown report saved to:[/green] {report_filepath}")
            except Exception as e:
                console.print(f"[bold red]Error saving markdown report:[/bold red] {e}")

        # If there were string errors encountered (from general Exceptions)
        if errors_encountered:
            # This part had syntax errors related to console.print and string formatting
            # Corrected to use a single multiline string for console.print
            console.print("\n[bold yellow]Encountered the following issues during processing:[/bold yellow]")
            for err in errors_encountered:
                console.print(f"- {err}")

        # Optionally save background report if configured
        if config.save_background_report:
            background_report_filename = f"background_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            background_report_filepath = os.path.join(config.output_dir, background_report_filename)
            if save_background_report(all_results, "Global Search", background_report_filepath):
                console.print(f"[green]Background scan report saved to:[/green] {background_report_filepath}")
            else:
                console.print("[bold red]Error saving background scan report.[/bold red]")

        # Interactive Exploration
        if args.interactive and all_results:
            while True:
                choices = [Choice(res['name'], name=res['name']) for res in all_results]
                choices.append(Choice(value="quit", name="[Quit]"))
                
                selected_repo_name = inquirer.select(
                    message="Select a repository to explore interactively:",
                    choices=choices
                ).execute()
                
                if selected_repo_name == "quit":
                    break
                
                # In this implementation, temp_repo_dir was reused. 
                # To make this robust, we'd need to re-clone or use persistent storage.
                # For now, we'll warn the user that only the LAST processed repo is in temp_repo_dir
                # OR we could modify process_repository to use unique dirs.
                
                # Optimization: Find if the selected repo is currently in the temp_repo_dir
                # (Since we reuse it, it's likely the last one)
                last_repo_name = all_results[-1]['name']
                if selected_repo_name == last_repo_name:
                    explore_repo_files(os.path.join(config.temp_dir, "repo_clone"))
                else:
                    console.print(f"[yellow]Note: Re-cloning {selected_repo_name} for exploration...[/yellow]")
                    temp_explore_dir = os.path.join(config.temp_dir, "explore")
                    shutil.rmtree(temp_explore_dir, ignore_errors=True)
                    os.makedirs(temp_explore_dir, exist_ok=True)
                    
                    repo_obj = next(r for r in repos_to_process if r.full_name == selected_repo_name)
                    subprocess.run(["git", "clone", "--depth", "1", repo_obj.clone_url, temp_explore_dir], check=True, capture_output=True)
                    explore_repo_files(temp_explore_dir)

    else: # This block handles the case where repos_to_process is empty
        # If repos_to_process is empty, it implies either search found no results or search failed.
        # If it succeeded but found 0 results, we should let the user know.
        console.print("[yellow]No repositories found matching the criteria.[/yellow]")
        pass # Rely on search_repositories to emit errors if it fails.


if __name__ == "__main__":
    # This is a simplified entry point. In a real CLI, this would be handled by cli.py
    # For demonstration, we'll directly call main()
    main()
