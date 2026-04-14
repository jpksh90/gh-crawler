# GH Crawler Pro 🚀

A high-performance GitHub repository crawler and AI-powered code analysis agent. Search across repositories and use a smart AI agent to perform deep-dive analysis on the discovered code.

## 🌟 Key Features

- **AI Code Agent:** Leverages Google's Gemini 1.5 Flash to intelligently explore and analyze cloned repositories.
- **Smart Tasking:** Instead of simple keyword matching, tell the agent exactly what you're looking for (e.g., *"Analyze the project's dependency management logic"*).
- **Live Agent Dashboard:** Real-time visibility into the agent's thought process, tool calls, and workspace status.
- **Interactive Deep-Dive:** Browse step-by-step reasoning logs and full execution traces after a scan.
- **Visual Exploration Tree:** See a visual hierarchy of every file the agent touched during its analysis.
- **Automated Reporting:** Generate comprehensive Markdown reports of your search findings and agent analysis.
- **Secure Persistence:** Store your GitHub and Google API keys securely in `~/.gh-crawler.json`.

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

### ⌨️ Interactive Menu Actions:
- `deep`: Inspect the full reasoning log and tool outputs for a specific repository.
- `tree`: Display a visual tree of files analyzed by the AI agent.
- `md`: Export a professional Markdown report of the session.
- `json`: Export raw scan results and traces.
- `quit`: Exit the session.

## 🔑 Configuration

The tool will prompt you for the following keys on its first run if they are not found in your environment:

- `GITHUB_TOKEN`: Personal Access Token for GitHub API (recommended to avoid rate limits).
- `GOOGLE_API_KEY`: API Key for Google Gemini (Gemini 1.5 Flash).

These are stored locally in `~/.gh-crawler.json`.

## 📂 Project Structure

- `src/github_crawler/main.py`: Main entry point and Agent implementation.
- `pyproject.toml`: Project metadata and dependencies.
- `README.md`: Documentation.

---
Built with ❤️ using Python, Rich, and Google Generative AI.
