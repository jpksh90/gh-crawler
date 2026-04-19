import html
import json
import os
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import parse_qs, urlparse

from rich.console import Console

from github_crawler.config import Config
from github_crawler.events import EventType, event_bus
from github_crawler.main import run_crawler

console = Console()

HTML_PAGE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>GH Crawler GUI</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #111827; color: #f9fafb; }
    header { padding: 16px 24px; background: #1f2937; border-bottom: 1px solid #374151; }
    main { display: grid; grid-template-columns: 420px 1fr; gap: 16px; padding: 16px; }
    .panel { background: #1f2937; border: 1px solid #374151; border-radius: 12px; padding: 16px; }
    h1, h2 { margin: 0 0 12px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    label { display: block; font-size: 0.9rem; margin-bottom: 4px; color: #d1d5db; }
    input, textarea { width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px; border: 1px solid #4b5563; background: #111827; color: #f9fafb; }
    textarea { min-height: 90px; resize: vertical; }
    .full { grid-column: 1 / -1; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    button, a.button { border: none; border-radius: 8px; padding: 10px 14px; cursor: pointer; background: #2563eb; color: white; text-decoration: none; display: inline-block; }
    button.secondary, a.secondary { background: #374151; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .status { margin: 12px 0; padding: 10px 12px; background: #0f172a; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #374151; }
    tr:hover { background: #111827; cursor: pointer; }
    pre { white-space: pre-wrap; word-break: break-word; background: #111827; border-radius: 8px; padding: 12px; min-height: 120px; }
    .stack { display: grid; gap: 16px; }
    .muted { color: #9ca3af; font-size: 0.9rem; }
  </style>
</head>
<body>
  <header>
    <h1>GH Crawler GUI</h1>
    <div class=\"muted\">Browser-based interface for configuring and running repository scans.</div>
  </header>
  <main>
    <section class=\"panel\">
      <h2>Scan Settings</h2>
      <div class=\"grid\">
        <div class=\"full\"><label>GitHub Token</label><input id=\"github_token\" type=\"password\" value=\"{{github_token}}\" /></div>
        <div class=\"full\"><label>Keywords</label><input id=\"keywords\" value=\"{{keywords}}\" /></div>
        <div><label>Language</label><input id=\"language\" value=\"{{language}}\" /></div>
        <div><label>License</label><input id=\"license\" value=\"{{license}}\" /></div>
        <div><label>Minimum Stars</label><input id=\"min_stars\" value=\"{{min_stars}}\" /></div>
        <div><label>Minimum Forks</label><input id=\"min_forks\" value=\"{{min_forks}}\" /></div>
        <div><label>Limit</label><input id=\"limit\" value=\"{{limit}}\" /></div>
        <div><label>Save Background Report</label><input id=\"save_background_report\" type=\"checkbox\" {{save_background_checked}} /></div>
        <div class=\"full\"><label>Task</label><textarea id=\"task\">{{task}}</textarea></div>
        <div class=\"full\"><label>Output Directory</label><input id=\"output_dir\" value=\"{{output_dir}}\" /></div>
        <div class=\"full\"><label>Temporary Directory</label><input id=\"temp_dir\" value=\"{{temp_dir}}\" /></div>
      </div>
      <div class=\"actions\">
        <button id=\"saveButton\" class=\"secondary\" onclick=\"saveConfig()\">Save Config</button>
        <button id=\"startButton\" onclick=\"startScan()\">Start Scan</button>
        <a id=\"markdownLink\" class=\"button secondary\" href=\"#\" style=\"display:none\">Download Markdown</a>
        <a id=\"backgroundLink\" class=\"button secondary\" href=\"#\" style=\"display:none\">Download Background Report</a>
      </div>
      <div id=\"message\" class=\"status\">Ready.</div>
      <pre id="progressSummary">Phase: idle
Current repository: none
Progress: 0/0
Last message: Ready.</pre>
    </section>
    <section class=\"stack\">
      <div class=\"panel\">
        <h2>Results</h2>
        <table>
          <thead>
            <tr><th>Repository</th><th>Stars</th><th>Language</th><th>Lines</th></tr>
          </thead>
          <tbody id=\"resultsBody\"></tbody>
        </table>
      </div>
      <div class=\"panel\">
        <h2>Details</h2>
        <pre id=\"details\">Select a repository to inspect the analysis.</pre>
      </div>
      <div class=\"panel\">
        <h2>Activity Log</h2>
        <pre id=\"logs\">Waiting for events...</pre>
      </div>
    </section>
  </main>
  <script>
    let selectedIndex = null;
    let lastState = null;

    function formPayload() {
      return {
        github_token: document.getElementById('github_token').value,
        keywords: document.getElementById('keywords').value,
        language: document.getElementById('language').value,
        license: document.getElementById('license').value,
        min_stars: document.getElementById('min_stars').value,
        min_forks: document.getElementById('min_forks').value,
        limit: document.getElementById('limit').value,
        save_background_report: document.getElementById('save_background_report').checked,
        task: document.getElementById('task').value,
        output_dir: document.getElementById('output_dir').value,
        temp_dir: document.getElementById('temp_dir').value,
      };
    }

    async function postJson(url, payload) {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Request failed');
      }
      return data;
    }

    async function saveConfig() {
      try {
        const result = await postJson('/api/config/save', formPayload());
        document.getElementById('message').textContent = result.message;
      } catch (error) {
        document.getElementById('message').textContent = error.message;
      }
    }

    async function startScan() {
      try {
        const result = await postJson('/api/scan/start', formPayload());
        document.getElementById('message').textContent = result.message;
      } catch (error) {
        document.getElementById('message').textContent = error.message;
      }
    }

    function renderDetails() {
      const details = document.getElementById('details');
      if (!lastState || selectedIndex === null || !lastState.results[selectedIndex]) {
        details.textContent = 'Select a repository to inspect the analysis.';
        return;
      }
      const result = lastState.results[selectedIndex];
      const trace = (result.trace || []).map(item => `Turn ${item.turn}: ${item.thought}\n${item.output}`).join('\n\n') || 'No trace data.';
      const filesTouched = (result.files_touched || []).slice().sort().join('\n') || 'None';
      details.textContent = [
        `Repository: ${result.name}`,
        `URL: ${result.url}`,
        `Stars: ${result.stars}`,
        `Language: ${result.language || 'Unknown'}`,
        `Lines of code: ${result.lines_of_code || 0}`,
        '',
        'Analysis:',
        result.analysis,
        '',
        'Files touched:',
        filesTouched,
        '',
        'Trace:',
        trace,
      ].join('\n');
    }

    function renderState(state) {
      lastState = state;
      const progress = state.progress || {};
      document.getElementById('message').textContent = state.status;
      document.getElementById('startButton').disabled = state.running;
      document.getElementById('saveButton').disabled = state.running;
      document.getElementById('logs').textContent = (state.logs || []).join('\n') || 'Waiting for events...';
      document.getElementById('progressSummary').textContent = [
        `Phase: ${progress.phase || 'idle'}`,
        `Current repository: ${progress.current_repo || 'none'}`,
        `Progress: ${progress.completed_repos || 0}/${progress.total_repos || 0}`,
        `Last message: ${progress.last_message || 'Ready.'}`,
      ].join('\n');

      const resultsBody = document.getElementById('resultsBody');
      resultsBody.innerHTML = '';
      (state.results || []).forEach((result, index) => {
        const row = document.createElement('tr');
        row.innerHTML = `<td>${result.name}</td><td>${result.stars}</td><td>${result.language || ''}</td><td>${result.lines_of_code || 0}</td>`;
        row.onclick = () => { selectedIndex = index; renderDetails(); };
        resultsBody.appendChild(row);
      });
      if (selectedIndex !== null && (!state.results || !state.results[selectedIndex])) {
        selectedIndex = null;
      }
      renderDetails();

      const markdownLink = document.getElementById('markdownLink');
      if (state.artifacts && state.artifacts.markdown_report) {
        markdownLink.href = '/download/markdown';
        markdownLink.style.display = 'inline-block';
      } else {
        markdownLink.style.display = 'none';
      }

      const backgroundLink = document.getElementById('backgroundLink');
      if (state.artifacts && state.artifacts.background_report) {
        backgroundLink.href = '/download/background';
        backgroundLink.style.display = 'inline-block';
      } else {
        backgroundLink.style.display = 'none';
      }
    }

    async function refreshState() {
      const response = await fetch('/api/state');
      const state = await response.json();
      renderState(state);
    }

    refreshState();
    setInterval(refreshState, 1000);
  </script>
</body>
</html>
"""


class BrowserGuiApp:
    def __init__(self):
        self.lock = threading.Lock()
        self.base_config = Config(args=None)
        self.running = False
        self.status = "Ready."
        self.logs = []
        self.results = []
        self.artifacts = {}
        self.current_task = "Analyze repository structure"
        self.phase = "idle"
        self.current_repo = None
        self.completed_repos = 0
        self.total_repos = 0
        self.last_message = "Ready."
        self.server = None
        self._subscribe_to_events()

    def _append_log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.last_message = message
        self.logs.append(f"[{timestamp}] {message}")
        self.logs = self.logs[-500:]

    def _subscribe_to_events(self):
        for event_type in EventType:
            event_bus.subscribe(event_type, self._build_listener(event_type))

    def _build_listener(self, event_type: EventType):
        def listener(data):
            self._record_event(event_type, data)

        return listener

    def _record_event(self, event_type: EventType, data):
        with self.lock:
            if event_type == EventType.SYNTHESIS_STARTED:
                self.phase = "synthesis"
                self.status = "Synthesizing search criteria..."
                self._append_log("Synthesizing search criteria...")
            elif event_type == EventType.SYNTHESIS_FINISHED:
                self.phase = "search"
                self.status = "Search criteria ready"
                if data:
                    self._append_log(
                        f"Using keywords={data.get('keywords', '')}, language={data.get('language', '')}, min_stars={data.get('min_stars', '')}"
                    )
            elif event_type == EventType.SEARCH_STARTED:
                self.phase = "search"
                self.status = "Searching GitHub..."
                self._append_log("Searching GitHub...")
            elif event_type == EventType.SEARCH_SUCCESS:
                self.total_repos = int(data or 0)
                self.status = f"Found {data} repositories"
                self._append_log(f"Found {data} repositories")
            elif event_type == EventType.PROCESSING_STARTED:
                self.phase = "processing"
                self.status = "Processing repositories..."
            elif event_type == EventType.PROCESSING_FINISHED:
                self.phase = "reporting"
                self.current_repo = None
                self.status = "Processing complete"
            elif event_type == EventType.REPO_START:
                self.phase = "processing"
                self.current_repo = data
                repo_position = self.completed_repos + 1
                if self.total_repos:
                    self.status = f"Processing {repo_position}/{self.total_repos}: {data}"
                else:
                    self.status = f"Processing {data}"
                self._append_log(f"Analyzing {data}...")
            elif event_type == EventType.REPO_SUCCESS:
                self.completed_repos += 1
                self._append_log(f"Finished {data}")
                if self.total_repos:
                    self.status = f"Completed {self.completed_repos}/{self.total_repos} repositories"
            elif event_type == EventType.REPO_ERROR:
                repo_name, error_details = data
                self.completed_repos += 1
                self._append_log(f"Error processing {repo_name or 'search'}: {error_details}")
            elif event_type == EventType.ERROR:
                self.phase = "error"
                self.status = "Error"
                self._append_log(f"ERROR: {data}")
            elif event_type == EventType.LOG:
                self._append_log(str(data))

    def _payload_to_config(self, payload):
        def parse_int(name, default):
            raw = payload.get(name, default)
            if raw in (None, ""):
                return default
            try:
                return int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name.replace('_', ' ').title()} must be an integer.") from exc

        def parse_bool(name, default):
            raw = payload.get(name, default)
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                return raw.strip().lower() in {"1", "true", "yes", "on"}
            return bool(raw)

        args = type("GuiArgs", (), {
            "github_token": (payload.get("github_token") or "").strip() or None,
            "keywords": (payload.get("keywords") or "").strip() or None,
            "language": (payload.get("language") or "").strip() or None,
            "min_stars": parse_int("min_stars", self.base_config.min_stars),
            "min_forks": parse_int("min_forks", self.base_config.min_forks),
            "license": (payload.get("license") or "").strip() or None,
            "limit": parse_int("limit", self.base_config.limit),
            "run_background": parse_bool("save_background_report", self.base_config.save_background_report),
        })()

        config = Config(args=args, config_file=self.base_config.config_file)
        config.output_dir = (payload.get("output_dir") or self.base_config.output_dir).strip()
        config.temp_dir = (payload.get("temp_dir") or self.base_config.temp_dir).strip()
        config.save_background_report = parse_bool("save_background_report", self.base_config.save_background_report)
        config.github_token = (payload.get("github_token") or config.github_token or "").strip() or None
        config.keywords = (payload.get("keywords") or config.keywords or "").strip() or None
        config.language = (payload.get("language") or config.language or "").strip() or None
        os.makedirs(config.output_dir, exist_ok=True)
        os.makedirs(config.temp_dir, exist_ok=True)
        return config

    def save_config(self, payload):
        config = self._payload_to_config(payload)
        config.save()
        with self.lock:
            self.base_config = config
            self.status = f"Configuration saved to {config.config_file}"
            self._append_log(self.status)
        return {"message": self.status}

    def start_scan(self, payload):
        with self.lock:
            if self.running:
                raise RuntimeError("A scan is already running.")

        config = self._payload_to_config(payload)
        if not config.github_token or not config.keywords:
            raise RuntimeError("GitHub token and keywords are required to run a scan.")

        config.save()
        with self.lock:
            self.base_config = config
            self.running = True
            self.phase = "starting"
            self.status = "Running scan..."
            self.logs = []
            self._append_log("Starting scan...")
            self.results = []
            self.artifacts = {}
            self.current_repo = None
            self.completed_repos = 0
            self.total_repos = 0
            self.current_task = (payload.get("task") or "Analyze repository structure").strip() or "Analyze repository structure"

        worker = threading.Thread(target=self._scan_worker, args=(config, self.current_task), daemon=True)
        worker.start()
        return {"message": "Scan started."}

    def _scan_worker(self, config, task):
        try:
            results, artifacts = run_crawler(
                config=config,
                task=task,
                interactive=False,
                render_console=False,
                save_reports=True,
            )
            with self.lock:
                self.results = results
                self.artifacts = artifacts
                self.phase = "complete"
                self.current_repo = None
                self.status = f"Completed: {len(results)} repositories"
                self._append_log("Scan completed.")
        except Exception as exc:
            with self.lock:
                self.phase = "error"
                self.status = f"Scan failed: {exc}"
                self._append_log(self.status)
        finally:
            with self.lock:
                self.running = False

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "status": self.status,
                "logs": list(self.logs),
                "results": list(self.results),
                "progress": {
                    "phase": self.phase,
                    "current_repo": self.current_repo,
                    "completed_repos": self.completed_repos,
                    "total_repos": self.total_repos,
                    "last_message": self.last_message,
                },
                "artifacts": {
                    name: bool(path) and os.path.exists(path)
                    for name, path in self.artifacts.items()
                },
            }

    def render_index(self):
        replacements = {
            "github_token": self.base_config.github_token or "",
            "keywords": self.base_config.keywords or "",
            "language": self.base_config.language or "",
            "license": self.base_config.license or "",
            "min_stars": str(self.base_config.min_stars),
            "min_forks": str(self.base_config.min_forks),
            "limit": str(self.base_config.limit),
            "task": self.current_task,
            "output_dir": self.base_config.output_dir,
            "temp_dir": self.base_config.temp_dir,
            "save_background_checked": "checked" if self.base_config.save_background_report else "",
        }
        page = HTML_PAGE
        for key, value in replacements.items():
            page = page.replace(f"{{{{{key}}}}}", html.escape(value, quote=True))
        return page.encode("utf-8")

    def download_artifact(self, name):
        with self.lock:
            artifact_path = self.artifacts.get(f"{name}_report")
        if not artifact_path or not os.path.exists(artifact_path):
            raise FileNotFoundError(f"No {name} artifact available.")
        return artifact_path

    def _json_response(self, handler, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        handler.send_response(status_code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _text_response(self, handler, status_code, body, content_type):
        handler.send_response(status_code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def build_handler(self):
        app = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    app._text_response(self, 200, app.render_index(), "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/state":
                    app._json_response(self, 200, app.snapshot())
                    return
                if parsed.path.startswith("/download/"):
                    name = parsed.path.rsplit("/", 1)[-1]
                    try:
                        artifact_path = app.download_artifact(name)
                        with open(artifact_path, "rb") as handle:
                            body = handle.read()
                        content_type = "text/markdown; charset=utf-8" if artifact_path.endswith(".md") else "text/plain; charset=utf-8"
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Disposition", f"attachment; filename={os.path.basename(artifact_path)}")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                    except FileNotFoundError as exc:
                        app._json_response(self, 404, {"error": str(exc)})
                    return
                app._json_response(self, 404, {"error": "Not found"})

            def do_POST(self):
                parsed = urlparse(self.path)
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length) if content_length else b"{}"
                try:
                    payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
                except json.JSONDecodeError:
                    payload = {key: values[0] for key, values in parse_qs(raw_body.decode("utf-8")).items()}

                try:
                    if parsed.path == "/api/config/save":
                        app._json_response(self, 200, app.save_config(payload))
                        return
                    if parsed.path == "/api/scan/start":
                        app._json_response(self, 200, app.start_scan(payload))
                        return
                    app._json_response(self, 404, {"error": "Not found"})
                except Exception as exc:
                    app._json_response(self, 400, {"error": str(exc)})

        return RequestHandler

    def serve(self, host="127.0.0.1", port=8765):
        handler_class = cast(type[BaseHTTPRequestHandler], self.build_handler())

        def handler_factory(*args):
            return handler_class(*args)

        self.server = ThreadingHTTPServer((host, port), handler_factory)
        url = f"http://{host}:{self.server.server_port}"
        console.print(f"[green]GUI available at:[/green] {url}")
        console.print("[dim]Press Ctrl+C to stop the GUI server.[/dim]")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopping GUI server...[/yellow]")
        finally:
            self.server.server_close()


def launch_gui():
    app = BrowserGuiApp()
    port = int(os.environ.get("GH_CRAWLER_GUI_PORT", "8765"))
    app.serve(port=port)
