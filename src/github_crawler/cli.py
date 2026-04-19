import argparse
import os
from rich.console import Console
from rich.tree import Tree
from rich.prompt import Prompt
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

def parse_args():
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
    parser.add_argument("--interactive", action="store_true", help="Interactively explore repositories after scanning.")
    
    # API Key Arguments
    parser.add_argument("--github-token", type=str, help="GitHub API token.")
    parser.add_argument("--google-api-key", type=str, help="Google API Key.")
    parser.add_argument("--openai-api-key", type=str, help="OpenAI API Key.")

    return parser.parse_args()

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

def add_tree_nodes(node, tree_data):
    # Sort to show dirs then files, alphabetically
    items = sorted(tree_data.items(), key=lambda x: (x[1] is None, x[0]))
    for name, content in items:
        if content is None: # File
            node.add(f"[green]{name}[/green]")
        else: # Directory
            sub_node = node.add(f"[bold blue]{name}/[/bold blue]")
            add_tree_nodes(sub_node, content)
