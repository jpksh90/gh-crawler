
from datetime import datetime
import json
import os
import shutil
import subprocess
import tempfile
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.text import Text
from rich.syntax import Syntax
from rich.pretty import Pretty
from github import Github, GithubException
from rich.markdown import Markdown
from pyfiglet import figlet_format
from rich.markup import escape
import yaml
import argparse
import time

# Assuming config.yaml exists and is loaded elsewhere, or defined here for example
# For this example, let's assume a dummy config loader or direct access
# In a real scenario, this would be properly handled.
try:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    config = {} # Or load defaults

# Import for the new rate limiter
from github_crawler.rate_limiter import TokenBucket

console = Console()

def save_config(new_config):
    # Placeholder for saving configuration
    # In a real application, this would write to a config file like config.yaml
    pass

class CodeAgent:
    def __init__(self, repo_name: str, repo_path: str, google_key: str):
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.google_key = google_key
        self.trace = []
        self.files_touched = set()
        self.current_task = ""

    def run_session(self, task: str, silent: bool = False):
        self.current_task = task
        self.trace.append({"turn": 1, "thought": "Initial thought process for the task.", "output": "Starting analysis..."})
        
        # Placeholder for actual analysis logic
        analysis_result = f"Analysis of '{self.repo_name}' for task: '{task}'. Initial step completed."
        self.trace.append({"turn": 1, "thought": "Completed initial analysis step.", "output": analysis_result})
        
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

def generate_markdown_report(results, task):
    md = f"# GH Crawler Smart Search Report\n\n"
    md += f"**Task:** {task}\n\n"
    md += f"**Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    for i, res in enumerate(results):
        md += f"## {i+1}. Repository: [{res['name']}]({res['url']})" + "\n"
        md += f"- **Stars:** {res['stars']}" + "\n"
        md += f"- **Language:** {res['language']}" + "\n"
        md += f"- **Lines of Code:** {res.get('lines_of_code', 0):,}" + "\n"
        md += f"- **Agent Analysis:** {res['analysis']}" + "\n"
        
        if res['trace']:
            md += "\n### Trace Log:\n"
            for t in res['trace']:
                md += f"- **Turn {t['turn']}**: Thought: {t['thought']} | Output: ```\n{t['output'][:200]}...\n```\n" # Truncate output for brevity
        
        if res['files_touched']:
            md += "\n### Files Touched:\n"
            for f in sorted(res["files_touched"]):
                md += f"- `{f}`" + "\n"
        md += "\n---\n\n"
    return md

def count_lines_of_code(repo_path: str):
    """
    Counts the total lines of code in the repository, excluding hidden files and directories.
    """
    total_lines = 0
    for root, dirs, files in os.walk(repo_path):
        # Exclude hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            # Exclude hidden files
            if file.startswith('.'):
                continue
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    total_lines += sum(1 for _ in f)
            except Exception:
                # Skip files that cannot be read
                continue
    return total_lines

def get_repo_tree(repo_path: str):
    """
    Captures the file tree structure of the repository.
    """
    tree_data = {}
    for root, dirs, files in os.walk(repo_path):
        # Exclude hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        rel_path = os.path.relpath(root, repo_path)
        if rel_path == ".":
            current = tree_data
        else:
            parts = rel_path.split(os.sep)
            current = tree_data
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        for file in files:
            if not file.startswith('.'):
                current[file] = None # Mark as file
    return tree_data

def explore_repo_files(repo_path: str):
    """
    Provides an interactive CLI interface to explore files in a repository.
    """
    current_dir = repo_path
    console.print(f"\n[bold cyan]Exploring repository at:[/bold cyan] {repo_path}")

    while True:
        try:
            tree = Tree(f"[bold cyan]{os.path.basename(current_dir)}[/bold cyan]")
            
            items = os.listdir(current_dir)
            items.sort()

            dirs = [item for item in items if os.path.isdir(os.path.join(current_dir, item))]
            files = [item for item in items if os.path.isfile(os.path.join(current_dir, item))]

            for d in dirs:
                tree.add(f"[bold blue]{d}[/bold blue]/")
            for f in files:
                tree.add(f"[green]{f}[/green]")

            console.print(tree)

            action = Prompt.ask(f"[bold blue]{current_dir}[/bold blue]")

            if action == "..":
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == os.path.dirname(repo_path) and current_dir == repo_path:
                    current_dir = repo_path
                else:
                    current_dir = parent_dir
            elif action == "quit":
                break
            elif os.path.isdir(os.path.join(current_dir, action)):
                current_dir = os.path.join(current_dir, action)
            elif os.path.isfile(os.path.join(current_dir, action)):
                file_path = os.path.join(current_dir, action)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    console.print(Panel(Syntax(content, "text", theme="monokai", line_numbers=True), title=f"[bold green]{action}[/bold green]"))
                except Exception as e:
                    console.print(f"[red]Error reading file {action}: {e}[/red]")
            else:
                console.print(f"[red]Invalid action or path: {action}[/red]")
        except Exception as e:
            console.print(f"[bold red]An error occurred during exploration:[/bold red] {e}")
            break

def main():
    errors_encountered = [] # List to collect errors

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="GitHub Repository Crawler and Analyzer")

    # Search Criteria Arguments
    parser.add_argument("--keywords", type=str, help="Keywords to search for repositories.")
    parser.add_argument("--language", type=str, help="Filter by programming language.")
    parser.add_argument("--min-stars", type=int, help="Minimum number of stars a repository must have.")
    parser.add_argument("--min-forks", type=int, help="Minimum number of forks a repository must have.")
    parser.add_argument("--license", type=str, help="Filter by license (e.g., mit, apache-2.0).")
    parser.add_argument("--created-after", type=str, help="Filter repositories created after a specific date (YYYY-MM-DD).")
    parser.add_argument("--pushed-after", type=str, help="Filter repositories last pushed after a specific date (YYYY-MM-DD).")
    
    # Task and Limit Arguments
    parser.add_argument("--task", type=str, help="The specific analysis task to perform on cloned repositories.")
    parser.add_argument("--limit", type=int, help="Maximum number of repositories to process.")
    parser.add_argument("--run-background", action="store_true", help="Run analysis in the background and save output to a file.")
    
    # API Key Arguments
    parser.add_argument("--github-token", type=str, help="GitHub API token.")
    parser.add_argument("--google-api-key", type=str, help="Google API Key.")

    args = parser.parse_args()
    # --- End Argument Parsing ---

    # Welcome Banner
    banner = figlet_format("GH Crawler")
    console.print(f"[bold magenta]{banner}[/bold magenta]")
    console.print("[italic cyan]Smart GitHub Repository Analyzer[/italic cyan]\n\n")

    # --- Configuration Loading and Precedence ---
    loaded_search_criteria = None
    cached_analysis = {} # Dictionary to hold cached results
    memory_file = ".gemini_project_memory.json"

    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r") as f:
                saved_data = json.load(f)
                if isinstance(saved_data, dict):
                    if "search_params" in saved_data:
                        loaded_search_criteria = saved_data["search_params"]
                    if "cached_analysis" in saved_data:
                        cached_analysis = saved_data["cached_analysis"]
        except (json.JSONDecodeError, IOError) as e:
            error_msg = f"Could not load saved configuration from {memory_file}: {e}"
            console.print(f"[yellow]Warning: {error_msg}[/yellow]")
            errors_encountered.append(error_msg) # Log error

    use_saved_criteria = False
    if loaded_search_criteria:
        use_saved_criteria = Confirm.ask("[bold]Saved search criteria found. Use them? (Y/n)[/bold]", default=True)
    
    # Determine API tokens, prioritizing CLI args, then config/env vars
    github_token = args.github_token or config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    google_key = args.google_api_key or config.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not github_token or not google_key:
        if Confirm.ask("[yellow]Missing tokens. Configure them now?[/yellow]"):
            github_token = Prompt.ask("GitHub Token", default=github_token or "", password=True)
            google_key = Prompt.ask("Google API Key", default=google_key or "", password=True)
            save_config({"GITHUB_TOKEN": github_token, "GOOGLE_API_KEY": google_key})
    console.print("\n") # Added spacing

    # Determine Search Parameters, prioritizing CLI args, then saved criteria, then interactive prompts
    keywords_val = args.keywords if args.keywords else loaded_search_criteria.get("keywords") if use_saved_criteria else None
    language_val = args.language if args.language else loaded_search_criteria.get("language") if use_saved_criteria else None
    min_stars_val = args.min_stars if args.min_stars is not None else loaded_search_criteria.get("min_stars") if use_saved_criteria else None
    min_forks_val = args.min_forks if args.min_forks is not None else loaded_search_criteria.get("min_forks") if use_saved_criteria else None
    license_filter_val = args.license if args.license else loaded_search_criteria.get("license_filter") if use_saved_criteria else None
    created_after_val = args.created_after if args.created_after else loaded_search_criteria.get("created_after") if use_saved_criteria else None
    pushed_after_val = args.pushed_after if args.pushed_after else loaded_search_criteria.get("pushed_after") if use_saved_criteria else None

    keywords = keywords_val if keywords_val is not None else Prompt.ask("[bold]Keywords (Tags)[/bold]", default="crawler")
    language = language_val if language_val is not None else Prompt.ask("[bold]Language[/bold] (optional)", default="")
    min_stars = IntPrompt.ask("[bold]Minimum Stars[/bold] (optional, e.g., 500)", default=min_stars_val if min_stars_val is not None else 0) if min_stars_val is None else min_stars_val
    min_forks = IntPrompt.ask("[bold]Minimum Forks[/bold] (optional, e.g., 100)", default=min_forks_val if min_forks_val is not None else 0) if min_forks_val is None else min_forks_val
    license_filter = Prompt.ask("[bold]License[/bold] (optional, e.g., mit, apache-2.0)", default=license_filter_val if license_filter_val is not None else "") if license_filter_val is None else license_filter_val
    created_after = Prompt.ask("[bold]Created After[/bold] (optional, YYYY-MM-DD)", default=created_after_val) if created_after_val is None else created_after_val
    pushed_after = Prompt.ask("[bold]Pushed After[/bold] (optional, YYYY-MM-DD)", default=pushed_after_val) if pushed_after_val is None else pushed_after_val

    task_val = args.task if args.task else loaded_search_criteria.get("task") if use_saved_criteria else None
    task = task_val if task_val is not None else Prompt.ask("[bold]Deep Search Task[/bold]", default="Find the core logic")

    limit_val = args.limit if args.limit is not None else loaded_search_criteria.get("limit") if use_saved_criteria else None
    limit = limit_val if limit_val is not None else IntPrompt.ask("[bold]Limit[/bold]", default=2)

    run_background = args.run_background # This is a flag, if set, it's True
    if not run_background: # If flag not set, check interactive prompt
        run_background_interactive = Confirm.ask("[bold azure]Run Agent in Background? (Output to file)[/bold azure]", default=False)
        run_background = run_background_interactive
    # --- End Configuration Loading ---

    # Collect current search parameters for saving
    current_search_params = {
        "keywords": keywords,
        "language": language,
        "min_stars": min_stars,
        "min_forks": min_forks,
        "license_filter": license_filter,
        "created_after": created_after,
        "pushed_after": pushed_after,
        "task": task, # Including task and limit for saving too
        "limit": limit,
    }

    # Prompt to save current search criteria
    prompt_to_save = True # Default to prompt
    # Check if any value differs from its absolute default to decide whether to prompt saving
    if not args.keywords and not args.language and args.min_stars is None and args.min_forks is None and not args.license and not args.created_after and not args.pushed_after and not args.task and args.limit is None and not args.run_background and not args.github_token and not args.google_api_key and not use_saved_criteria:
        # If no CLI args were given, no saved criteria were loaded, and all inputs are at their absolute defaults, don't prompt to save.
        prompt_to_save = False
    
    if prompt_to_save and Confirm.ask("[bold]Save these search criteria for future use? (Y/n)[/bold]", default=False):
        try:
            # Save combined configuration: search params and current cache state
            all_config_data = {
                "search_params": current_search_params,
                "cached_analysis": cached_analysis # Save current cache state
            }
            with open(memory_file, "w") as f:
                json.dump(all_config_data, f, indent=4)
            console.print("[green]Search criteria and cache saved successfully.[/green]")
        except Exception as e:
            error_msg = f"Error saving configuration to {memory_file}: {e}"
            console.print(f"[bold red]{error_msg}[/bold red]")
            errors_encountered.append(error_msg)

    g = Github(github_token) if github_token else Github()
    # Instantiate Token Bucket for GitHub API requests
    token_bucket = TokenBucket(capacity=5, fill_rate=1.4) 
    results = []
    
    # --- Advanced GitHub API Error Handling with Retries ---
    max_retries = 5
    retry_delay_seconds = 5
    
    repositories = None
    repos_to_process = []

    for attempt in range(max_retries):
        try:
            # Wait for a token before making the GitHub API call
            console.print("[cyan]Attempting to acquire token for GitHub search...[/cyan]")
            if token_bucket.get_token():
                # --- Wrapping the actual API call ---
                try:
                    query_parts = [keywords]
                    if language: query_parts.append(f"language:{language}")
                    if min_stars > 0: query_parts.append(f"stars:>{min_stars}")
                    if min_forks > 0: query_parts.append(f"forks:>{min_forks}")
                    if license_filter: query_parts.append(f"license:{license_filter}")
                    if created_after: query_parts.append(f"created:>{created_after}")
                    if pushed_after: query_parts.append(f"pushed:>{pushed_after}")
                    query = " ".join(query_parts)

                    repositories = g.search_repositories(query=query)
                    
                    if repositories:
                        repos_to_process = [repositories[i] for i in range(min(limit, repositories.totalCount))]
                        console.print(f"[green]Successfully retrieved {len(repos_to_process)} repositories.[/green]")
                        break # Success, exit retry loop
                    else:
                        console.print("[yellow]Search returned no repositories. Exiting.[/yellow]")
                        break
                        
                except GithubException as e:
                    if e.status == 403: # Rate limit or forbidden
                        message = e.data.get('message', 'N/A')
                        error_msg = f"Rate limit hit or forbidden (403). Status: {message}. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                        console.print(f"[yellow]{error_msg}[/yellow]")
                        time.sleep(retry_delay_seconds)
                    elif 500 <= e.status < 600: # Temporary server errors
                        error_msg = f"GitHub API temporary error ({e.status}). Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                        console.print(f"[yellow]{error_msg}[/yellow]")
                        time.sleep(retry_delay_seconds)
                    else: # Other GithubExceptions, treat as non-recoverable for this loop
                        error_msg = f"Unhandled GitHub API error ({e.status}): {e.data.get('message', 'N/A')}. Aborting."
                        console.print(f"[bold red]{error_msg}[/bold red]")
                        errors_encountered.append(error_msg)
                        return # Exit if unrecoverable
                except Exception as e: # Catch other potential errors like network issues
                    error_msg = f"An unexpected error occurred during search: {e}. Retrying in {retry_delay_seconds}s... (Attempt {attempt + 1}/{max_retries})"
                    console.print(f"[yellow]{error_msg}[/yellow]")
                    time.sleep(retry_delay_seconds)

            else: # Token bucket failed
                error_msg = "Failed to acquire token for GitHub search within timeout. Aborting."
                console.print(f"[bold red]{error_msg}[/bold red]")
                errors_encountered.append(error_msg)
                return # Exit if token acquisition fails

        except Exception as e: # Catch errors related to token bucket itself or other unexpected issues
            error_msg = f"An error occurred before GitHub API call: {e}. Aborting."
            console.print(f"[bold red]{error_msg}[/bold red]")
            errors_encountered.append(error_msg)
            return

    if not repos_to_process: # If loop finished without success
        error_msg = "Failed to retrieve repositories after multiple retries. Aborting."
        console.print(f"[bold red]{error_msg}[/bold red]")
        errors_encountered.append(error_msg)
        return
    # --- End Advanced GitHub API Error Handling ---

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        for repo in repos_to_process:
            cache_key = f"{repo.full_name}:{task}" # Cache key combines repo name and task

            if cache_key in cached_analysis:
                console.print(f"[yellow]Using cached results for {repo.full_name} (Task: {task}).[/yellow]")
                cached_result = cached_analysis[cache_key]
                results.append(cached_result)
                continue

            # --- Cache Miss: Proceed with cloning and analysis ---
            if run_background:
                progress.add_task(description=f"Background Agent Analysis for {repo.full_name}...", total=None)
            
            temp_dir = tempfile.mkdtemp()
            repo_result = None # Initialize repo_result
            try:
                subprocess.run(["git", "clone", "--depth", "1", repo.ssh_url, temp_dir], check=True, capture_output=True)
                agent = CodeAgent(repo.full_name, temp_dir, google_key)
                analysis = agent.run_session(task, silent=run_background)
                
                repo_result = {
                    "name": repo.full_name,
                    "url": repo.html_url,
                    "stars": repo.stargazers_count,
                    "language": repo.language or "N/A",
                    "lines_of_code": count_lines_of_code(temp_dir),
                    "repo_tree": get_repo_tree(temp_dir),
                    "analysis": analysis,
                    "trace": agent.trace,
                    "files_touched": list(agent.files_touched)
                }
                results.append(repo_result)

                # Add to cache after successful analysis
                cached_analysis[cache_key] = repo_result

                # --- Interactive File Exploration ---
                if not run_background: # Only offer exploration if not running in background
                    if Confirm.ask("[bold]Explore cloned repository files interactively? (Y/n)[/bold]", default=False):
                        explore_repo_files(temp_dir)
            except Exception as e: # Catch errors during cloning/analysis for a specific repo
                error_msg = f"Error processing repository {repo.full_name}: {e}"
                console.print(f"[red]{error_msg}[/red]")
                errors_encountered.append(error_msg)
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    console.print("\n") # Added spacing before results table

    # Main Results Table
    table = Table(title="\nGlobal Search Results", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim")
    table.add_column("Repository", style="cyan")
    table.add_column("Lines", style="green")
    table.add_column("Agent Analysis", style="italic")

    for i, res in enumerate(results):
        table.add_row(str(i+1), res["name"], f"{res.get('lines_of_code', 0):,}", res["analysis"])
    console.print(table)

    # If background mode, automatically save to text file
    if run_background:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f"agent_results_{ts}.txt"
        try:
            with open(log_file, "w") as f:
                f.write(f"GH CRAWLER BACKGROUND SCAN REPORT - {ts}\n")
                f.write(f"Task: {task}\n")
                f.write("="*50 + "\n\n")
                for res in results:
                    f.write(f"REPO: {res['name']} ({res['url']})\n")
                    f.write(f"STARS: {res['stars']} | LANG: {res['language']} | LINES: {res.get('lines_of_code', 0):,}\n")
                    f.write(f"ANALYSIS: {res['analysis']}\n")
                    f.write("-" * 30 + "\n\n")
            console.print(f"[bold green]Background scan complete. Results saved to {log_file}[/bold green]")
        except Exception as e:
            error_msg = f"Error writing background results to {log_file}: {e}"
            console.print(f"[red]{error_msg}[/red]")
            errors_encountered.append(error_msg)

    console.print("\n") # Added spacing before post-scan menu

    # --- Save Final Configuration (including updated cache) ---
    final_search_params = {
        "keywords": keywords,
        "language": language,
        "min_stars": min_stars,
        "min_forks": min_forks,
        "license_filter": license_filter,
        "created_after": created_after,
        "pushed_after": pushed_after,
        "task": task,
        "limit": limit,
    }
    
    # Check if prompt to save is needed (based on if anything changed from defaults/loaded)
    prompt_to_save = True # Default to prompt
    # If no CLI args, no loaded criteria, and all inputs are at their absolute defaults, don't prompt to save.
    if not args.keywords and not args.language and args.min_stars is None and args.min_forks is None and not args.license and not args.created_after and not args.pushed_after and not args.task and args.limit is None and not args.run_background and not args.github_token and not args.google_api_key and not use_saved_criteria:
        prompt_to_save = False
    
    if prompt_to_save and Confirm.ask("[bold]Save current configuration (search params & cache) for future use? (Y/n)[/bold]", default=False):
        try:
            all_config_data = {
                "search_params": final_search_params,
                "cached_analysis": cached_analysis # Save the updated cache
            }
            with open(memory_file, "w") as f:
                json.dump(all_config_data, f, indent=4)
            console.print("[green]Configuration (search params & cache) saved successfully.[/green]")
        except Exception as e:
            error_msg = f"Error saving configuration to {memory_file}: {e}"
            console.print(f"[bold red]{error_msg}[/bold red]")
            errors_encountered.append(error_msg)
    # --- End Save Final Configuration ---

    # --- Report any collected errors ---
    if errors_encountered:
        console.print("\n[bold orange]--- Encountered Errors ---[/bold orange]")
        for i, err in enumerate(errors_encountered):
            console.print(f"[orange]{i+1}. {err}[/orange]")
        console.print("[bold orange]------------------------[/bold orange]")
    # --- End Error Reporting ---

    # Post-Scan Menu
    console.print("\n[bold cyan]Post-Scan Actions:[/bold cyan]")
    console.print("  [bold]deep[/bold]: Show full agent thought trace and analysis steps.")
    console.print("  [bold]tree[/bold]: Show complete repository file structure (directories and files).")
    console.print("  [bold]json[/bold]: Export all raw results to a JSON file (includes trace and tree).")
    console.print("  [bold]md[/bold]:   Generate a formatted Markdown report for sharing.")

    while True:
        choice = Prompt.ask(
            "\n[bold azure]Action[/bold azure]", 
            choices=["deep", "tree", "json", "md", "quit"], 
            default="quit"
        )
        if choice == "quit": break
        
        if choice in ["deep", "tree"]:
            idx = IntPrompt.ask("Enter Repo ID", default=1) - 1
            if 0 <= idx < len(results):
                res = results[idx]
                if choice == "deep":
                    for t in res["trace"]:
                        console.print(Panel(f"[bold dim]Turn {t['turn']} Thought:[/bold dim]\n{t['thought']}\n\n[bold dim]Output:[/bold dim]\n{escape(t['output'][:500])}...", title=f"Trace Log: {res['name']}"))
                else:
                    def add_tree_nodes(node, tree_data):
                        # Sort to show dirs then files, alphabetically
                        items = sorted(tree_data.items(), key=lambda x: (x[1] is None, x[0]))
                        for name, content in items:
                            if content is None: # File
                                node.add(f"[green]{name}[/green]")
                            else: # Directory
                                sub_node = node.add(f"[bold blue]{name}/[/bold blue]")
                                add_tree_nodes(sub_node, content)

                    tree = Tree(f"[bold cyan]{res['name']}[/bold cyan] (Project Structure)")
                    if "repo_tree" in res:
                        add_tree_nodes(tree, res["repo_tree"])
                    else:
                        for f in sorted(res.get("files_touched", [])):
                            tree.add(f"[green]{f}[/green]")
                    console.print(tree)
            else:
                console.print("[red]Invalid ID[/red]")
        elif choice == "json":
            filename = f"gh_pro_{datetime.now().strftime('%H%M%S')}.json"
            try:
                with open(filename, "w") as f: json.dump(results, f, indent=4)
                console.print(f"[green]Saved to {filename}[/green]")
            except Exception as e:
                error_msg = f"Error saving results to JSON {filename}: {e}"
                console.print(f"[red]{error_msg}[/red]")
                errors_encountered.append(error_msg)

        elif choice == "md":
            filename = f"report_{datetime.now().strftime('%H%M%S')}.md"
            try:
                with open(filename, "w") as f: f.write(generate_markdown_report(results, task))
                console.print(f"[green]Report saved to {filename}[/green]")
            except Exception as e:
                error_msg = f"Error saving report to Markdown {filename}: {e}"
                console.print(f"[red]{error_msg}[/red]")
                errors_encountered.append(error_msg)

if __name__ == "__main__":
    main()
