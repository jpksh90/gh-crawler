import os
import json
import shutil
import tempfile
import time
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.tree import Tree
from rich.markup import escape
from pyfiglet import figlet_format
from github import Github, GithubException

from github_crawler.rate_limiter import TokenBucket
from github_crawler.search import SearchSynthesizer
from github_crawler.agent import CodeAgent
from github_crawler.github_utils import count_lines_of_code, get_repo_tree, clone_repo
from github_crawler.config import load_yaml_config, save_config, load_project_memory, save_project_memory
from github_crawler.reporting import generate_markdown_report, display_results_table, save_background_report
from github_crawler.cli import parse_args, explore_repo_files, add_tree_nodes

console = Console()

def main():
    errors_encountered = []
    args = parse_args()
    config = load_yaml_config()

    # Welcome Banner
    banner = figlet_format("GH Crawler")
    console.print(f"[bold magenta]{banner}[/bold magenta]")
    console.print("[italic cyan]Smart GitHub Repository Analyzer[/italic cyan]\n\n")

    # --- Configuration Loading ---
    memory_file = ".gemini_project_memory.json"
    project_memory = load_project_memory(memory_file)
    loaded_search_criteria = project_memory.get("search_params")
    cached_analysis = project_memory.get("cached_analysis", {})

    use_saved_criteria = False
    if loaded_search_criteria:
        use_saved_criteria = Confirm.ask("[bold]Saved search criteria found. Use them? (Y/n)[/bold]", default=True)
    
    # Determine API tokens
    github_token = args.github_token or config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    google_key = args.google_api_key or config.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    openai_key = args.openai_api_key or config.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")

    if not github_token or (not google_key and not openai_key):
        if Confirm.ask("[yellow]Missing tokens. Configure them now?[/yellow]"):
            github_token = Prompt.ask("GitHub Token", default=github_token or "", password=True)
            if not google_key and not openai_key:
                google_key = Prompt.ask("Google API Key (optional if OpenAI key provided)", default=google_key or "", password=True)
                if not google_key:
                    openai_key = Prompt.ask("OpenAI API Key", default=openai_key or "", password=True)
            
            save_config({
                "GITHUB_TOKEN": github_token,
                "GOOGLE_API_KEY": google_key,
                "OPENAI_API_KEY": openai_key
            })
    console.print("\n")

    # Determine Search Parameters
    keywords_val = args.keywords if args.keywords else loaded_search_criteria.get("keywords") if use_saved_criteria else None
    language_val = args.language if args.language else loaded_search_criteria.get("language") if use_saved_criteria else None
    min_stars_val = args.min_stars if args.min_stars is not None else loaded_search_criteria.get("min_stars") if use_saved_criteria else None
    min_forks_val = args.min_forks if args.min_forks is not None else loaded_search_criteria.get("min_forks") if use_saved_criteria else None
    license_filter_val = args.license if args.license else loaded_search_criteria.get("license_filter") if use_saved_criteria else None
    created_after_val = args.created_after if args.created_after else loaded_search_criteria.get("created_after") if use_saved_criteria else None
    pushed_after_val = args.pushed_after if args.pushed_after else loaded_search_criteria.get("pushed_after") if use_saved_criteria else None
    task_val = args.task if args.task else loaded_search_criteria.get("task") if use_saved_criteria else None

    task = task_val
    keywords = keywords_val
    language = language_val
    min_stars = min_stars_val
    min_forks = min_forks_val
    license_filter = license_filter_val

    # Synthesis logic
    if (google_key or openai_key) and not keywords_val and not language_val:
        if task is None:
            task = Prompt.ask("[bold]Deep Search Task[/bold]", default="Find the core logic")
        
        if Confirm.ask("[bold magenta]Synthesize interesting search patterns from your Deep Search Task? (Y/n)[/bold magenta]", default=True):
            with console.status("[bold cyan]Synthesizing search patterns...[/bold cyan]"):
                synthesizer = SearchSynthesizer(google_key=google_key, openai_key=openai_key)
                synth_params = synthesizer.synthesize(task)
                
                keywords = synth_params.get("keywords", keywords)
                language = synth_params.get("language", language)
                min_stars = synth_params.get("min_stars", min_stars)
                min_forks = synth_params.get("min_forks", min_forks)
                license_filter = synth_params.get("license", license_filter)
                
                reasoning = synth_params.get("reasoning", "No reasoning provided.")
                console.print(Panel(f"[bold green]Synthesized Search Criteria:[/bold green]\n"
                                    f"[cyan]Keywords:[/cyan] {keywords}\n"
                                    f"[cyan]Language:[/cyan] {language}\n"
                                    f"[cyan]Min Stars:[/cyan] {min_stars}\n"
                                    f"[cyan]Reasoning:[/cyan] {reasoning}"))

    # Fallback to interactive prompts
    keywords = keywords if keywords is not None else Prompt.ask("[bold]Keywords (Tags)[/bold]", default="crawler")
    language = language if language is not None else Prompt.ask("[bold]Language[/bold] (optional)", default="")
    min_stars = IntPrompt.ask("[bold]Minimum Stars[/bold]", default=min_stars if min_stars is not None else 0)
    min_forks = IntPrompt.ask("[bold]Minimum Forks[/bold]", default=min_forks if min_forks is not None else 0)
    license_filter = Prompt.ask("[bold]License[/bold]", default=license_filter if license_filter is not None else "")
    created_after = created_after_val or Prompt.ask("[bold]Created After[/bold] (YYYY-MM-DD)", default="")
    pushed_after = pushed_after_val or Prompt.ask("[bold]Pushed After[/bold] (YYYY-MM-DD)", default="")

    if task is None:
        task = Prompt.ask("[bold]Deep Search Task[/bold]", default="Find the core logic")

    limit_val = args.limit if args.limit is not None else loaded_search_criteria.get("limit") if use_saved_criteria else None
    limit = limit_val if limit_val is not None else IntPrompt.ask("[bold]Limit[/bold]", default=2)

    run_background = args.run_background or (not args.run_background and Confirm.ask("[bold azure]Run Agent in Background?[/bold azure]", default=False))

    # Save Configuration
    current_search_params = {
        "keywords": keywords, "language": language, "min_stars": min_stars,
        "min_forks": min_forks, "license_filter": license_filter,
        "created_after": created_after, "pushed_after": pushed_after,
        "task": task, "limit": limit,
    }

    if Confirm.ask("[bold]Save these search criteria for future use? (Y/n)[/bold]", default=False):
        save_project_memory({"search_params": current_search_params, "cached_analysis": cached_analysis}, memory_file)

    # GitHub Search
    g = Github(github_token)
    token_bucket = TokenBucket(capacity=5, fill_rate=1.4) 
    results = []
    
    repos_to_process = []
    max_retries = 5
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            if token_bucket.get_token():
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
                    break
            else:
                time.sleep(retry_delay)
        except GithubException as e:
            console.print(f"[yellow]GitHub API error: {e}. Retrying...[/yellow]")
            time.sleep(retry_delay)

    if not repos_to_process:
        console.print("[bold red]No repositories found or API error. Aborting.[/bold red]")
        return

    # Processing Repositories
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as progress:
        for repo in repos_to_process:
            cache_key = f"{repo.full_name}:{task}"
            if cache_key in cached_analysis:
                console.print(f"[yellow]Using cached results for {repo.full_name}.[/yellow]")
                results.append(cached_analysis[cache_key])
                continue

            if run_background:
                progress.add_task(description=f"Analyzing {repo.full_name}...", total=None)
            
            temp_dir = tempfile.mkdtemp()
            try:
                clone_repo(repo.ssh_url, temp_dir)
                agent = CodeAgent(repo.full_name, temp_dir, google_key, openai_key)
                analysis = agent.run_session(task, silent=run_background)
                
                repo_result = {
                    "name": repo.full_name, "url": repo.html_url, "stars": repo.stargazers_count,
                    "language": repo.language or "N/A", "lines_of_code": count_lines_of_code(temp_dir),
                    "repo_tree": get_repo_tree(temp_dir), "analysis": analysis,
                    "trace": agent.trace, "files_touched": list(agent.files_touched)
                }
                results.append(repo_result)
                cached_analysis[cache_key] = repo_result

                if not run_background and Confirm.ask(f"[bold]Explore {repo.full_name} files? (Y/n)[/bold]", default=False):
                    explore_repo_files(temp_dir)
            except Exception as e:
                errors_encountered.append(f"Error processing {repo.full_name}: {e}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # Reporting
    display_results_table(results)
    if run_background:
        log_file = f"agent_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        if save_background_report(results, task, log_file):
            console.print(f"[bold green]Results saved to {log_file}[/bold green]")

    save_project_memory({"search_params": current_search_params, "cached_analysis": cached_analysis}, memory_file)

    if errors_encountered:
        console.print("\n[bold orange]--- Encountered Errors ---[/bold orange]")
        for err in errors_encountered: console.print(f"[orange]- {err}[/orange]")

    # Post-Scan Menu
    while True:
        choice = Prompt.ask("\n[bold azure]Action[/bold azure]", choices=["deep", "tree", "json", "md", "quit"], default="quit")
        if choice == "quit": break
        
        if choice in ["deep", "tree"]:
            idx = IntPrompt.ask("Enter Repo ID", default=1) - 1
            if 0 <= idx < len(results):
                res = results[idx]
                if choice == "deep":
                    for t in res["trace"]:
                        console.print(Panel(f"[bold dim]Turn {t['turn']} Thought:[/bold dim]\n{t['thought']}\n\n[bold dim]Output:[/bold dim]\n{escape(t['output'][:500])}...", title=f"Trace: {res['name']}"))
                else:
                    tree = Tree(f"[bold cyan]{res['name']}[/bold cyan] (Project Structure)")
                    add_tree_nodes(tree, res.get("repo_tree", {}))
                    console.print(tree)
            else:
                console.print("[red]Invalid ID[/red]")
        elif choice == "json":
            filename = f"gh_pro_{datetime.now().strftime('%H%M%S')}.json"
            with open(filename, "w") as f: json.dump(results, f, indent=4)
            console.print(f"[green]Saved to {filename}[/green]")
        elif choice == "md":
            filename = f"report_{datetime.now().strftime('%H%M%S')}.md"
            with open(filename, "w") as f: f.write(generate_markdown_report(results, task))
            console.print(f"[green]Report saved to {filename}[/green]")

if __name__ == "__main__":
    main()
