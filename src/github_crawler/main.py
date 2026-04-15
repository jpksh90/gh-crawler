import os
import json
import shutil
import tempfile
import subprocess
from datetime import datetime
from github import Github, GithubException

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markup import escape
from rich.live import Live
from rich.layout import Layout
from rich.tree import Tree
from rich import print as rprint

# For Smart Search Agent
import google.generativeai as genai

console = Console()
CONFIG_FILE = os.path.expanduser("~/.gh-crawler.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

class CodeAgent:
    """An AI agent that can search and analyze code with workspace tracking."""
    
    def __init__(self, repo_name: str, repo_path: str, api_key: str):
        self.repo_name = repo_name
        self.repo_path = repo_path
        genai.configure(api_key=api_key)
        
        # Robust model selection
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            model_to_use = next((m for m in available_models if 'gemini-1.5-flash' in m), 'gemini-1.5-flash')
        except Exception:
            model_to_use = 'gemini-1.5-flash'
        
        system_instruction = f"""
        You are a Smart Code Search Agent. Your goal is to analyze the local repository at '{repo_path}'.
        You have access to the following 'tools' via plain text commands:
        - LS: Lists files in a directory (e.g., 'LS src/').
        - READ: Reads the content of a file (e.g., 'READ src/main.py').
        - GREP: Searches for a pattern in the repo (e.g., 'GREP "def main"').
        - DONE: Final result found (e.g., 'DONE The auth logic is in src/auth.py').

        When you want to use a tool, output ONLY the tool command and wait.
        Example: LS src/
        """
        
        self.model = genai.GenerativeModel(
            model_name=model_to_use,
            system_instruction=system_instruction
        )
        self.chat = self.model.start_chat(history=[])
        self.trace = [] # Full log of thoughts and tool outputs
        self.files_touched = set()
        self.current_action = "Initializing..."
        self.last_tool_output = ""

    def tool_ls(self, path: str = "."):
        self.current_action = f"Listing files in {path}"
        full_path = os.path.join(self.repo_path, path)
        try:
            items = os.listdir(full_path)
            res = f"Files in {path}: " + ", ".join(items)
            self.last_tool_output = res
            return res
        except Exception as e:
            return f"Error listing {path}: {str(e)}"

    def tool_read(self, file_path: str):
        self.current_action = f"Reading {file_path}"
        self.files_touched.add(file_path)
        full_path = os.path.join(self.repo_path, file_path)
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                res = f"Content of {file_path}:\n{content[:1500]}..."
                self.last_tool_output = res
                return res
        except Exception as e:
            return f"Error reading {file_path}: {str(e)}"

    def tool_grep(self, pattern: str):
        self.current_action = f"Grepping for '{pattern}'"
        try:
            result = subprocess.run(
                ["grep", "-rn", pattern, self.repo_path],
                capture_output=True, text=True, errors='ignore'
            )
            res = f"Grep results for '{pattern}':\n{result.stdout[:1500]}"
            self.last_tool_output = res
            return res
        except Exception as e:
            return f"Error grepping {pattern}: {str(e)}"

    def make_dashboard(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1)
        )
        layout["main"].split_row(
            Layout(name="thoughts", ratio=1),
            Layout(name="status", ratio=1)
        )
        
        layout["header"].update(Panel(f"[bold cyan]Agent analyzing: {self.repo_name}[/bold cyan]", border_style="cyan"))
        thought_log = "\n".join([f"> {t['thought'][:100]}..." for t in self.trace[-5:]])
        layout["thoughts"].update(Panel(thought_log or "Waiting for first thought...", title="Recent Thoughts"))
        
        status_text = f"[bold azure]Current Action:[/bold azure] {self.current_action}\n"
        status_text += f"[bold azure]Files Touched:[/bold azure] {len(self.files_touched)}\n"
        status_text += f"[bold azure]Last Output Snippet:[/bold azure]\n{escape(self.last_tool_output[:200])}..."
        layout["status"].update(Panel(status_text, title="Workspace Status"))
        
        return layout

    def run_session(self, task: str, silent: bool = False):
        current_prompt = f"TASK: {task}\n\nAnalyze the repo and find the answer. Use LS, READ, or GREP as needed."
        
        def process_turn(turn, prompt):
            try:
                response_obj = self.chat.send_message(prompt)
                response = response_obj.text.strip()
            except Exception as e:
                return f"Model Error: {str(e)}", True
            
            self.trace.append({"turn": turn+1, "thought": response, "output": ""})
            
            if response.startswith("DONE"):
                final_msg = response[5:].strip()
                self.trace[-1]["output"] = final_msg
                return final_msg, True
            
            if response.startswith("LS"):
                output = self.tool_ls(response[3:].strip() or ".")
            elif response.startswith("READ"):
                output = self.tool_read(response[5:].strip())
            elif response.startswith("GREP"):
                output = self.tool_grep(response[5:].strip().strip('"'))
            else:
                output = "Unknown tool call. Use LS, READ, GREP, or DONE."
            
            self.trace[-1]["output"] = output
            return f"TOOL OUTPUT:\n{output}\n\nNext step?", False

        if silent:
            for turn in range(12):
                res, is_done = process_turn(turn, current_prompt)
                if is_done: return res
                current_prompt = res
        else:
            with Live(self.make_dashboard(), refresh_per_second=4) as live:
                for turn in range(12):
                    res, is_done = process_turn(turn, current_prompt)
                    live.update(self.make_dashboard())
                    if is_done: return res
                    current_prompt = res
        
        return "Agent timed out."

def generate_markdown_report(results, task):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = f"# GH Crawler Smart Search Report\n"
    md += f"Generated on: {timestamp}\n\n"
    md += f"## Task: {task}\n\n"
    
    for res in results:
        md += f"### [{res['name']}]({res['url']})\n"
        md += f"- **Stars:** {res['stars']}\n"
        md += f"- **Language:** {res['language']}\n"
        md += f"#### Agent Analysis:\n{res['analysis']}\n\n"
        md += f"#### Files Touched:\n"
        for f in res['files_touched']:
            md += f"- `{f}`\n"
        md += "\n---\n\n"
    return md

def main():
    config = load_config()
    
    console.print(Panel.fit(
        "[bold cyan]GH CRAWLER PRO[/bold cyan]\n[dim]Agentic Search & Deep Analysis[/dim]", 
        border_style="cyan"
    ))

    # Token/API Key Configuration
    github_token = config.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    google_key = config.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not github_token or not google_key:
        if Confirm.ask("[yellow]Missing tokens. Configure them now?[/yellow]"):
            github_token = Prompt.ask("GitHub Token", default=github_token or "", password=True)
            google_key = Prompt.ask("Google API Key", default=google_key or "", password=True)
            save_config({"GITHUB_TOKEN": github_token, "GOOGLE_API_KEY": google_key})

    # Interactive Inputs
    keywords = Prompt.ask("[bold]Keywords (Tags)[/bold]", default="crawler")
    language = Prompt.ask("[bold]Language[/bold] (optional)", default="")
    task = Prompt.ask("[bold]Deep Search Task[/bold]", default="Find the core logic")
    limit = IntPrompt.ask("[bold]Limit[/bold]", default=2)
    run_background = Confirm.ask("[bold azure]Run Agent in Background? (Output to file)[/bold azure]", default=False)
    
    g = Github(github_token) if github_token else Github()
    results = []
    
    try:
        query = keywords + (f" language:{language}" if language else "")
        repositories = g.search_repositories(query=query)
        repos_to_process = [repositories[i] for i in range(min(limit, repositories.totalCount))]
    except Exception as e:
        console.print(f"[bold red]Search Error:[/bold red] {e}")
        return

    # Use Progress if in background
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        for repo in repos_to_process:
            if run_background:
                progress.add_task(description=f"Background Agent Analysis for {repo.full_name}...", total=None)
            
            temp_dir = tempfile.mkdtemp()
            try:
                subprocess.run(["git", "clone", "--depth", "1", repo.ssh_url, temp_dir], check=True, capture_output=True)
                agent = CodeAgent(repo.full_name, temp_dir, google_key)
                analysis = agent.run_session(task, silent=run_background)
                
                results.append({
                    "name": repo.full_name,
                    "url": repo.html_url,
                    "stars": repo.stargazers_count,
                    "language": repo.language or "N/A",
                    "analysis": analysis,
                    "trace": agent.trace,
                    "files_touched": list(agent.files_touched)
                })
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    # Main Results Table
    table = Table(title="\nGlobal Search Results", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim")
    table.add_column("Repository", style="cyan")
    table.add_column("Agent Analysis", style="italic")

    for i, res in enumerate(results):
        table.add_row(str(i+1), res["name"], res["analysis"])
    console.print(table)

    # If background mode, automatically save to text file
    if run_background:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = f"agent_results_{ts}.txt"
        with open(log_file, "w") as f:
            f.write(f"GH CRAWLER BACKGROUND SCAN REPORT - {ts}\n")
            f.write(f"Task: {task}\n")
            f.write("="*50 + "\n\n")
            for res in results:
                f.write(f"REPO: {res['name']} ({res['url']})\n")
                f.write(f"STARS: {res['stars']} | LANG: {res['language']}\n")
                f.write(f"ANALYSIS: {res['analysis']}\n")
                f.write("-" * 30 + "\n\n")
        console.print(f"[bold green]Background scan complete. Results saved to {log_file}[/bold green]")

    # Post-Scan Menu
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
                    tree = Tree(f"[bold cyan]{res['name']}[/bold cyan] (Files Touched)")
                    for f in sorted(res["files_touched"]):
                        tree.add(f"[green]{f}[/green]")
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
