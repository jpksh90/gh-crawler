# GH Crawler

An interactive GitHub repository crawler built with Python and [Textual](https://textual.textualize.io/).

## Features
- **Interactive TUI:** Real-time search and browsing.
- **Traceability:** Detailed trace information for every repository.
- **Responsive Design:** Side-by-side view of results and details.

## Installation

To install this tool globally:

```bash
uv tool install . --force
```

## Usage

Simply run the command to launch the interactive interface:

```bash
gh-crawler
```

### Controls:
- **Keywords:** Enter keywords to search for.
- **Language:** (Optional) Filter by programming language.
- **Limit:** (Optional) Maximum number of results to fetch.
- **Search:** Click the Search button or press Enter in the input fields.
- **Select:** Use arrow keys and Enter to select a repository and see its details and trace.
- **Quit:** Press `q` to exit.

## Authentication

Set the `GITHUB_TOKEN` environment variable to increase rate limits:

```bash
export GITHUB_TOKEN=your_token_here
gh-crawler
```
