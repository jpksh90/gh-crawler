# GH Crawler Pro 🚀

A GitHub repository crawler with a natural-language interface for discovering relevant repositories, cloning them into a persisted session workspace, and scanning their source code for requested properties.

## 🌟 Key Features

- **Natural-Language Repository Discovery:** Describe the kind of projects you want, and the crawler turns that into a GitHub search query.
- **Session Workspaces:** Each scan keeps its cloned repositories under `output/sessions/<session-id>/clones/` so you can inspect them later in the same session.
- **Source Property Scanner:** Describe the code properties you want to inspect and the crawler returns concrete file/line evidence from cloned repositories.
- **Live Agent Dashboard:** Real-time visibility into the agent's thought process, tool calls, and workspace status.
- **Interactive Deep-Dive:** Browse step-by-step reasoning logs and full execution traces after a scan.
- **Visual Exploration Tree:** See a visual hierarchy of every file the agent touched during its analysis.
- **Automated Reporting:** Generate comprehensive Markdown reports of your search findings and agent analysis.
- **Secure Persistence:** Store your GitHub crawler settings locally in `~/.gh-crawler.yaml`.

## 🛠️ Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed, then run:

```bash
uv tool install . --force
```

## 🚀 Usage

Launch the interactive CLI by simply running:

```bash
gh-crawler
```

Launch the browser-based GUI alternative with:

```bash
gh-crawler -g
```

Example CLI usage:

```bash
gh-crawler \
  --keywords "Find actively maintained Python graph database projects" \
  --task "Look for JWT authentication, middleware, and authorization decorators"
```

Manage persisted sessions:

```bash
gh-crawler --list-sessions
gh-crawler --delete-session session-20260419T120000Z
```

### ⌨️ Interactive Menu Actions:
- `deep`: Inspect the full reasoning log and tool outputs for a specific repository.
- `tree`: Display a visual tree of files analyzed by the AI agent.
- `md`: Export a professional Markdown report of the session.
- `json`: Export raw scan results and traces.
- `quit`: Exit the session.

## 🔑 Configuration

The tool will prompt you for the following keys on its first run if they are not found in your environment:

- `GITHUB_TOKEN`: Personal Access Token for GitHub API (recommended to avoid rate limits).
- `GOOGLE_API_KEY`: Optional API key for richer search synthesis.
- `OPENAI_API_KEY`: Optional API key for richer search synthesis.

These are stored locally in `~/.gh-crawler.yaml`.

## 📂 Project Structure

- `src/github_crawler/main.py`: Main entry point and scan orchestration.
- `src/github_crawler/source_scan.py`: Deterministic source-property scanner for cloned repositories.
- `src/github_crawler/session_store.py`: Session workspace persistence and archiving helpers.
- `pyproject.toml`: Project metadata and dependencies.
- `README.md`: Documentation.

---
Built with ❤️ using Python, Rich, and Google Generative AI.
