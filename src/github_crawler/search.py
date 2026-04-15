import google.generativeai as genai
import openai
import json
from typing import List, Dict, Any, Optional

class SearchSynthesizer:
    def __init__(self, google_key: Optional[str] = None, openai_key: Optional[str] = None):
        self.google_key = google_key
        self.openai_key = openai_key
        
        if google_key:
            genai.configure(api_key=google_key)
            self.google_model = genai.GenerativeModel('gemini-1.5-flash')
        
        if openai_key:
            self.openai_client = openai.OpenAI(api_key=openai_key)

    def synthesize(self, deep_query: str) -> Dict[str, Any]:
        """
        Synthesizes structured search parameters from a deep query.
        Returns a dictionary compatible with GitHub repository search.
        """
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

        Example:
        Query: "Find modern async Python web frameworks with OIDC support"
        Output:
        {{
            "keywords": "async oidc python web framework",
            "language": "python",
            "min_stars": 100,
            "reasoning": "Looking for Python frameworks with 'async' and 'oidc' as core features."
        }}
        """
        
        try:
            if self.openai_key:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that helps developers find GitHub repositories."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={ "type": "json_object" }
                )
                text = response.choices[0].message.content
            elif self.google_key:
                response = self.google_model.generate_content(prompt)
                text = response.text.strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
            else:
                raise ValueError("No API key provided for synthesis.")
            
            data = json.loads(text)
            return data
        except Exception as e:
            # Fallback in case of error
            return {
                "keywords": deep_query,
                "reasoning": f"Fallback due to synthesis error: {str(e)}"
            }
