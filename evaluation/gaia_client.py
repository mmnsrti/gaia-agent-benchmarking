import requests
from typing import List, Dict, Any

DEFAULT_API_URL = "https://agents-course-unit4-scoring.hf.space"


class GAIAClient:
    """Client for interacting with the Hugging Face Agents Course GAIA scoring backend."""

    def __init__(self, api_url: str = DEFAULT_API_URL):
        self.api_url = api_url.rstrip("/")

    def get_questions(self) -> List[Dict[str, Any]]:
        """Fetches all evaluation questions from the scoring backend."""
        url = f"{self.api_url}/questions"
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()

    def get_random_question(self) -> Dict[str, Any]:
        """Fetches a random evaluation question from the backend."""
        url = f"{self.api_url}/random-question"
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.json()

    def download_file(self, task_id: str) -> bytes:
        """Downloads an attached file for a specific task if available."""
        url = f"{self.api_url}/files/{task_id}"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content

    def submit_answers(self, username: str, agent_code: str, answers: List[Dict[str, str]]) -> Dict[str, Any]:
        """Submits answers to the scoring API to receive an official score."""
        url = f"{self.api_url}/submit"
        payload = {
            "username": username.strip(),
            "agent_code": agent_code.strip(),
            "answers": answers,
        }
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
