import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import openai
from github import Github
from google import genai

from github_crawler.events import EventType, event_bus

class AIProvider(ABC):
    @abstractmethod
    def synthesize(self, prompt: str) -> str:
        pass

class GoogleAIProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    def synthesize(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt
        )
        if not response.text:
            return "{}"
            
        text = response.text.strip()
        
        # More robust JSON extraction using regex
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
            
        json_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
            
        return text

class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)

    def synthesize(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that helps developers find GitHub repositories."},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" }
        )
        if not response.choices:
            return "{}"
        return response.choices[0].message.content

class SearchSynthesizer:
    def __init__(self, google_key: Optional[str] = None, openai_key: Optional[str] = None):
        self.provider: Optional[AIProvider] = None
        
        if openai_key:
            self.provider = OpenAIProvider(openai_key)
        elif google_key:
            self.provider = GoogleAIProvider(google_key)

    def synthesize(self, deep_query: str) -> Dict[str, Any]:
        if not self.provider:
            return {
                "keywords": deep_query,
                "reasoning": "No AI provider configured for synthesis; using the repository request verbatim.",
            }

        prompt = f"""
        Analyze the following deep query and extract interesting search patterns for GitHub repositories.
        The goal is to find repositories that best match the user's intent.
        
        Deep Query: "{deep_query}"
        
        Provide the output in JSON format with the following keys:
        - keywords: (str) A string of space-separated keywords/tags for general search.
        - labels: (list[str]) Specific labels or categories that best describe the repository's purpose or technology.
        - language: (str, optional) The primary programming language.
        - min_stars: (int, optional) Minimum number of stars.
        - min_forks: (int, optional) Minimum number of forks.
        - license: (str, optional) License type (e.g., mit, apache-2.0).
        - reasoning: (str) A brief explanation of why these parameters were chosen.

        Example:
        Query: "Find modern async Python web frameworks with OIDC support"
        Output:
        {{
            "keywords": "async python web framework",
            "labels": ["web", "framework", "python", "oidc"],
            "language": "python",
            "min_stars": 100,
            "reasoning": "Looking for Python frameworks with 'async' and 'oidc' as core features."
        }}
        """
        
        try:
            text = self.provider.synthesize(prompt)
            if not text or text.strip() == "":
                raise ValueError("Provider returned empty response.")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("Provider returned non-object JSON.")
            if not payload.get("keywords"):
                raise ValueError("Provider response did not include keywords.")
            return payload
        except Exception as e:
            raise ValueError(
                f"Synthesis error via {self.provider.__class__.__name__}: {str(e)}"
            )

class GitHubSearcher:
    def __init__(self, token: str):
        self.gh = Github(token, timeout=15)

    def search_repositories(self, keywords: str, labels: Optional[List[str]] = None, language: Optional[str] = None,
                            min_stars: Optional[int] = None, min_forks: Optional[int] = None,
                            license: Optional[str] = None, limit: Optional[int] = None) -> List[Any]:
        query = keywords
        for label in labels or []:
            query += f" topic:{label}"
        if language:
            query += f" language:{language}"
        if min_stars:
            query += f" stars:>={min_stars}"
        if min_forks:
            query += f" forks:>={min_forks}"
        if license:
            query += f" license:{license}"
        
        event_bus.emit(EventType.LOG, f"Sending search query to GitHub: {query}")
        repositories = self.gh.search_repositories(query=query)
        # Convert PaginatedList to a regular list (limiting based on config)
        results = []
        try:
            for i, repo in enumerate(repositories):
                if limit is not None and i >= limit:
                    break
                results.append(repo)
                event_bus.emit(EventType.LOG, f"Found repository: {repo.full_name}")
        except Exception as e:
            raise e
        return results
