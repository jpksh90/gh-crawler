import os
import re
from typing import Any, Dict, Iterable, List, Sequence


MAX_FILE_SIZE = 512 * 1024
MAX_FINDINGS = 25
TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".idea",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
SEMANTIC_HINTS = {
    "auth": ["auth", "oauth", "openid", "jwt", "session", "login", "token"],
    "database": ["database", "sql", "postgres", "mysql", "sqlite", "orm", "migration"],
    "api": ["api", "rest", "graphql", "router", "endpoint", "handler"],
    "queue": ["queue", "worker", "job", "task", "consumer", "producer"],
    "config": ["config", "settings", "env", "dotenv", "yaml", "toml"],
    "security": ["security", "sanitize", "csrf", "xss", "encryption", "secret"],
}
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "code",
    "does",
    "find",
    "for",
    "how",
    "in",
    "look",
    "me",
    "of",
    "or",
    "project",
    "repositories",
    "repository",
    "search",
    "show",
    "specific",
    "source",
    "that",
    "the",
    "their",
    "these",
    "this",
    "to",
    "uses",
    "using",
    "with",
}


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def plan_property_query(query: str) -> Dict[str, Any]:
    normalized_query = (query or "").strip()
    quoted_terms = [
        match[0] or match[1]
        for match in re.findall(r'"([^"]+)"|\'([^\']+)\'', normalized_query)
    ]
    regex_patterns = re.findall(r"/([^/\n]{2,})/", normalized_query)
    token_candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_.:/-]{2,}", normalized_query.lower())
    token_terms = [token for token in token_candidates if token not in STOP_WORDS]
    semantic_terms: List[str] = []
    for semantic_key, hints in SEMANTIC_HINTS.items():
        if semantic_key in normalized_query.lower():
            semantic_terms.extend(hints)

    terms = _dedupe([*quoted_terms, *token_terms[:12], *semantic_terms])
    compiled_regexes = []
    for pattern in regex_patterns:
        compiled_regexes.append({"pattern": pattern, "compiled": re.compile(pattern, re.IGNORECASE)})

    return {
        "query": normalized_query,
        "terms": terms[:15],
        "regexes": compiled_regexes,
        "reasoning": "Matched literal identifiers, quoted phrases, regexes, and semantic hints from the natural-language property request.",
    }


def _iter_files(repo_path: str) -> Iterable[str]:
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [entry for entry in dirs if entry not in IGNORED_DIRECTORIES and not entry.startswith(".")]
        for file_name in files:
            if file_name.startswith("."):
                continue
            _, extension = os.path.splitext(file_name)
            if extension.lower() not in TEXT_EXTENSIONS:
                continue
            file_path = os.path.join(root, file_name)
            try:
                if os.path.getsize(file_path) > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            yield file_path


def _snippet(lines: Sequence[str], line_number: int) -> str:
    start = max(0, line_number - 2)
    end = min(len(lines), line_number + 1)
    return "\n".join(line.rstrip() for line in lines[start:end]).strip()


class SourcePropertyScanner:
    def __init__(self, repo_name: str, repo_path: str):
        self.repo_name = repo_name
        self.repo_path = repo_path

    def scan(self, query: str) -> Dict[str, Any]:
        plan = plan_property_query(query)
        findings: List[Dict[str, Any]] = []
        files_touched = set()

        for file_path in _iter_files(self.repo_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
                    lines = handle.readlines()
            except OSError:
                continue

            relative_path = os.path.relpath(file_path, self.repo_path)
            matched_in_file = False
            for line_number, line in enumerate(lines, start=1):
                lower_line = line.lower()
                for term in plan["terms"]:
                    if term.lower() in lower_line:
                        findings.append(
                            {
                                "file_path": relative_path,
                                "line_number": line_number,
                                "match_type": "term",
                                "pattern": term,
                                "snippet": _snippet(lines, line_number),
                            }
                        )
                        matched_in_file = True
                for regex_info in plan["regexes"]:
                    if regex_info["compiled"].search(line):
                        findings.append(
                            {
                                "file_path": relative_path,
                                "line_number": line_number,
                                "match_type": "regex",
                                "pattern": regex_info["pattern"],
                                "snippet": _snippet(lines, line_number),
                            }
                        )
                        matched_in_file = True
                if len(findings) >= MAX_FINDINGS:
                    break
            if matched_in_file:
                files_touched.add(relative_path)
            if len(findings) >= MAX_FINDINGS:
                break

        summary = self._build_summary(plan, findings, files_touched)
        trace = [
            {
                "turn": 1,
                "thought": "Converted the natural-language property request into literal terms, semantic hints, and optional regex patterns.",
                "output": f"terms={plan['terms']}, regexes={[entry['pattern'] for entry in plan['regexes']]}",
            },
            {
                "turn": 2,
                "thought": "Scanned text-like source and configuration files in the cloned repository for matching evidence.",
                "output": summary,
            },
        ]
        return {
            "summary": summary,
            "trace": trace,
            "files_touched": sorted(files_touched),
            "findings": findings,
            "plan": {
                "query": plan["query"],
                "terms": plan["terms"],
                "regexes": [entry["pattern"] for entry in plan["regexes"]],
                "reasoning": plan["reasoning"],
            },
        }

    def _build_summary(self, plan: Dict[str, Any], findings: List[Dict[str, Any]], files_touched: set[str]) -> str:
        if not findings:
            return (
                f"No direct evidence for '{plan['query']}' was found in {self.repo_name}. "
                f"Searched for {len(plan['terms'])} literal terms and {len(plan['regexes'])} regex patterns."
            )

        examples = ", ".join(
            f"{finding['file_path']}:{finding['line_number']}"
            for finding in findings[:3]
        )
        return (
            f"Found {len(findings)} matches across {len(files_touched)} files for '{plan['query']}'. "
            f"Top evidence: {examples}."
        )
