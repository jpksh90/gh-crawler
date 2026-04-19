from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

def generate_markdown_report(results, task):
    md = "# GH Crawler Smart Search Report\n\n"
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

def display_results_table(results):
    table = Table(title="\nGlobal Search Results", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim")
    table.add_column("Repository", style="cyan")
    table.add_column("Lines", style="green")
    table.add_column("Agent Analysis", style="italic")

    for i, res in enumerate(results):
        table.add_row(str(i+1), res["name"], f"{res.get('lines_of_code', 0):,}", res["analysis"])
    console.print(table)

def save_background_report(results, task, log_file):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
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
        return True
    except Exception:
        return False
