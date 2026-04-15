import json
import google.generativeai as genai
import openai
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class AIProvider(ABC):
    @abstractmethod
    def synthesize(self, prompt: str) -> str:
        pass

class GoogleAIProvider(AIProvider):
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def synthesize(self, prompt: str) -> str:
        response = self.model.generate_content(prompt)
        text = response.text.strip()
        # Clean up potential markdown wrapping
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
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
        return response.choices[0].message.content

class SearchSynthesizer:
    def __init__(self, google_key: Optional[str] = None, openai_key: Optional[str] = None):
        self.provider: Optional[AIProvider] = None
        
        # Priority: OpenAI then Google (Strategy selection)
        if openai_key:
            self.provider = OpenAIProvider(openai_key)
        elif google_key:
            self.provider = GoogleAIProvider(google_key)

    def synthesize(self, deep_query: str) -> Dict[str, Any]:
        if not self.provider:
            return {
                "keywords": deep_query,
                "reasoning": "No AI provider configured for synthesis."
            }

        prompt = f"""
        Analyze the following deep query and extract interesting search patterns for GitHub repositories.
        The goal is to find repositories that best match the user's intent.
        
        Deep Query: "{deep_query}"
        
        Provide the output in JSON format with the following keys:
        - keywords: (str) A string of space-separated keywords/tags.
        - language: (str, optional) The primary programming language.
        - min_stars: (int, optional) Minimum number of stars.
        - min_forks: (int, optional) Minimum number of forks.
        - license: (str, optional) License type (e.g., mit, apache-2.0).
        - reasoning: (str) A brief explanation of why these parameters were chosen.
        """
        
        try:
            text = self.provider.synthesize(prompt)
            return json.loads(text)
        except Exception as e:
            return {
                "keywords": deep_query,
                "reasoning": f"Synthesis error via {self.provider.__class__.__name__}: {str(e)}"
            }
