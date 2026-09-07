"""Unit tests for V1 Web Search tool, agent, and evaluation pipeline.

All tests use mocks to ensure no external network requests or Tavily API keys are needed.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from tools.web_search import TavilySearchTool, WebSearchResult, SearchResultItem
from agent.agent import GAIAAgent, GAIAWebAgent, AgentResult
from agent.llm import LLMResponse
from prompts.baseline import PROMPT_VERSION as BASELINE_PROMPT_VERSION
from prompts.web_search import WEB_SEARCH_PROMPT_VERSION
from evaluation.runner import execute_task
from evaluation.evaluate import calculate_metrics
from evaluation.dataset import GAIATask
from evaluation.metrics import gaia_question_scorer


class MockLLMClient:
    """Mock LLM client returning configurable LLMResponse."""

    def __init__(self, response_text: str = "42", finish_reason: str = "STOP"):
        self.model = "gemini-3.5-flash-lite"
        self.temperature = None
        self.max_output_tokens = 2048
        self.thinking_level = "medium"
        self.response = LLMResponse(
            text=response_text,
            raw_text=response_text,
            finish_reason=finish_reason,
            input_tokens=15,
            output_tokens=3,
            thinking_tokens=50,
            total_tokens=68,
            response_id="mock-resp-id",
            model_version="gemini-3.5-flash-lite",
        )
        self.last_prompt = None

    def generate(self, prompt: str) -> LLMResponse:
        self.last_prompt = prompt
        return self.response


class TestTavilySearchTool(unittest.TestCase):
    """Tests for the TavilySearchTool provider abstraction."""

    @patch("tools.web_search.TavilyClient")
    def test_successful_search(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {
                    "title": "Python Programming",
                    "url": "https://www.python.org",
                    "content": "Python is a high-level programming language.",
                    "score": 0.98,
                },
                {
                    "title": "Python Tutorial",
                    "url": "https://docs.python.org",
                    "content": "Official Python documentation and tutorials.",
                    "score": 0.95,
                },
            ]
        }

        tool = TavilySearchTool(api_key="fake-test-key")
        result = tool.search("What is Python?")

        self.assertTrue(result.success)
        self.assertEqual(result.query, "What is Python?")
        self.assertEqual(len(result.results), 2)
        self.assertEqual(result.results[0].title, "Python Programming")
        self.assertEqual(result.results[0].url, "https://www.python.org")
        self.assertIn("Python is a high-level", result.results[0].content)
        self.assertEqual(result.call_count, 1)
        self.assertEqual(result.provider, "tavily")
        self.assertEqual(result.search_depth, "basic")
        self.assertEqual(result.max_results, 5)
        self.assertIsNone(result.error_type)
        self.assertIsNone(result.error_message)

    @patch("tools.web_search.TavilyClient")
    def test_empty_search_results(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        tool = TavilySearchTool(api_key="fake-test-key")
        result = tool.search("xyzabcnonexistentquery12345")

        self.assertTrue(result.success)
        self.assertEqual(len(result.results), 0)
        self.assertEqual(result.format_evidence_block(), "No web search results found.")

    @patch("tools.web_search.TavilyClient")
    def test_search_api_failure(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search.side_effect = RuntimeError("503 Service Unavailable")

        tool = TavilySearchTool(api_key="fake-test-key")
        result = tool.search("What is Python?")

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "RuntimeError")
        self.assertIn("503 Service Unavailable", result.error_message)
        self.assertEqual(len(result.results), 0)

    def test_missing_api_key_fails_gracefully(self):
        with patch.dict(os.environ, {}, clear=True):
            tool = TavilySearchTool(api_key=None)
            result = tool.search("What is Python?")

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "MissingAPIKeyError")
            self.assertIn("TAVILY_API_KEY is not set", result.error_message)

    def test_empty_query_fails_gracefully(self):
        tool = TavilySearchTool(api_key="fake-key")
        result = tool.search("   ")

        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "EmptyQueryError")

    @patch("tools.web_search.TavilyClient")
    def test_deterministic_tavily_parameters(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search.return_value = {"results": []}

        tool = TavilySearchTool(api_key="fake-key", max_results=5, search_depth="basic")
        tool.search("test query")

        mock_client.search.assert_called_once_with(
            query="test query",
            search_depth="basic",
            max_results=5,
            include_answer=False,
            include_raw_content=False,
            include_images=False,
            auto_parameters=False,
        )

    def test_result_formatting(self):
        result = WebSearchResult(
            query="test query",
            results=[
                SearchResultItem(title="Title 1", url="https://example1.com", content="Snippet 1"),
                SearchResultItem(title="Title 2", url="https://example2.com", content="Snippet 2"),
            ],
            success=True,
        )
        formatted = result.format_evidence_block()
        self.assertIn("[1] Title: Title 1", formatted)
        self.assertIn("URL: https://example1.com", formatted)
        self.assertIn("Snippet: Snippet 1", formatted)
        self.assertIn("[2] Title: Title 2", formatted)
        self.assertIn("URL: https://example2.com", formatted)
        self.assertIn("Snippet: Snippet 2", formatted)


class TestGAIAWebAgent(unittest.TestCase):
    """Tests for the V1 GAIAWebAgent and retrieval execution flow."""

    def test_exactly_one_search_call_per_task(self):
        mock_tool = MagicMock()
        mock_tool.search.return_value = WebSearchResult(
            query="test",
            results=[SearchResultItem(title="T", url="U", content="C")],
            success=True,
            latency_seconds=0.5,
        )
        mock_tool.format_evidence.return_value = "[1] Title: T\n    URL: U\n    Snippet: C"

        llm = MockLLMClient(response_text="Final answer: 42")
        agent = GAIAWebAgent(llm_client=llm, search_tool=mock_tool)

        result = agent.run("What is 6 times 7?")

        self.assertEqual(mock_tool.search.call_count, 1)
        self.assertEqual(result.final_answer, "42")
        self.assertFalse(result.search_fallback)

    def test_original_question_used_as_query_without_rewriting(self):
        mock_tool = MagicMock()
        mock_tool.search.return_value = WebSearchResult(
            query="original",
            results=[],
            success=True,
        )

        llm = MockLLMClient(response_text="42")
        agent = GAIAWebAgent(llm_client=llm, search_tool=mock_tool)

        raw_question = "In what year did Neil Armstrong land on the moon?"
        agent.run(raw_question)

        # Must pass the exact original question string to search
        mock_tool.search.assert_called_once_with(raw_question)

    def test_fallback_to_llm_only_on_search_failure(self):
        mock_tool = MagicMock()
        mock_tool.search.return_value = WebSearchResult(
            query="test",
            results=[],
            success=False,
            error_type="HTTPError",
            error_message="503 Service Unavailable",
        )

        llm = MockLLMClient(response_text="Rome")
        agent = GAIAWebAgent(llm_client=llm, search_tool=mock_tool)

        result = agent.run("What is the capital of Italy?")

        self.assertTrue(result.search_fallback)
        self.assertEqual(result.prompt_version, BASELINE_PROMPT_VERSION)
        self.assertEqual(result.final_answer, "Rome")
        self.assertIn("Answer the following question accurately.", result.prompt)
        self.assertNotIn("Web Search Evidence:", result.prompt)

    def test_v1_prompt_version_recorded_on_success(self):
        mock_tool = MagicMock()
        mock_tool.search.return_value = WebSearchResult(
            query="test",
            results=[SearchResultItem(title="Capital Guide", url="https://capitals.org", content="The capital of Italy is Rome.")],
            success=True,
            latency_seconds=0.3,
        )

        llm = MockLLMClient(response_text="Rome")
        agent = GAIAWebAgent(llm_client=llm, search_tool=mock_tool)

        result = agent.run("What is the capital of Italy?")

        self.assertFalse(result.search_fallback)
        self.assertEqual(result.prompt_version, WEB_SEARCH_PROMPT_VERSION)
        self.assertIn("Web Search Evidence:", result.prompt)
        self.assertIn("The capital of Italy is Rome.", result.prompt)
        self.assertEqual(result.final_answer, "Rome")


class TestV1ExecutionAndLogging(unittest.TestCase):
    """Tests for runner metadata logging and safe public summary evaluation."""

    @patch("evaluation.runner.get_git_metadata")
    def test_search_metadata_logging_in_execute_task(self, mock_git):
        mock_git.return_value = {"git_commit": "abc1234", "git_branch": "v1-web-search", "git_dirty": False}

        mock_tool = MagicMock()
        mock_tool.search.return_value = WebSearchResult(
            query="Who wrote Hamlet?",
            results=[
                SearchResultItem(title="Hamlet Info", url="https://shakes.org", content="Written by William Shakespeare", score=0.99)
            ],
            success=True,
            latency_seconds=0.42,
            call_count=1,
            provider="tavily",
        )

        llm = MockLLMClient(response_text="William Shakespeare")
        agent = GAIAWebAgent(llm_client=llm, search_tool=mock_tool)

        record = execute_task(
            task_id="task-lit-01",
            question="Who wrote Hamlet?",
            level=1,
            agent=agent,
            llm=llm,
            project_version="v1",
        )

        self.assertEqual(record["project_version"], "v1")
        self.assertEqual(record["prompt_version"], WEB_SEARCH_PROMPT_VERSION)
        self.assertTrue(record["search_enabled"])
        self.assertEqual(record["search_provider"], "tavily")
        self.assertEqual(record["search_query"], "Who wrote Hamlet?")
        self.assertEqual(record["search_call_count"], 1)
        self.assertTrue(record["search_success"])
        self.assertEqual(record["search_latency_seconds"], 0.42)
        self.assertEqual(record["search_result_count"], 1)
        self.assertFalse(record["search_fallback"])
        self.assertIsNone(record["search_error_type"])
        self.assertEqual(len(record["search_results"]), 1)
        self.assertEqual(record["search_results"][0]["title"], "Hamlet Info")
        self.assertEqual(record["final_answer"], "William Shakespeare")

    def test_private_search_details_not_leaked_into_public_summary(self):
        tasks_by_id = {
            "t1": GAIATask("t1", "Question 1?", 1, "Ans1"),
            "t2": GAIATask("t2", "Question 2?", 1, "Ans2"),
        }
        predictions = [
            {
                "task_id": "t1",
                "level": 1,
                "project_version": "v1",
                "final_answer": "Ans1",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 2.0,
                "search_enabled": True,
                "search_provider": "tavily",
                "search_query": "Question 1?",
                "search_call_count": 1,
                "search_success": True,
                "search_latency_seconds": 0.45,
                "search_result_count": 5,
                "search_fallback": False,
                "search_results": [{"title": "Private Title 1", "url": "https://secret.org", "content": "Private snippet 1"}],
            },
            {
                "task_id": "t2",
                "level": 1,
                "project_version": "v1",
                "final_answer": "Wrong",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 2.2,
                "search_enabled": True,
                "search_provider": "tavily",
                "search_query": "Question 2?",
                "search_call_count": 1,
                "search_success": False,
                "search_latency_seconds": 0.10,
                "search_result_count": 0,
                "search_fallback": True,
                "search_error_type": "HTTPError",
                "search_error_message": "Rate limit",
                "search_results": [],
            },
        ]

        metrics = calculate_metrics(
            predictions=predictions,
            tasks_by_id=tasks_by_id,
            level=1,
            project_version="v1",
        )

        summary = metrics["summary"]
        detailed = metrics["detailed"]

        # Aggregate fields present in summary
        self.assertEqual(summary["project_version"], "v1")
        self.assertTrue(summary["search_enabled"])
        self.assertEqual(summary["search_provider"], "tavily")
        self.assertEqual(summary["total_search_calls"], 2)
        self.assertEqual(summary["successful_search_calls"], 1)
        self.assertEqual(summary["search_success_rate"], 0.5)
        self.assertAlmostEqual(summary["average_search_latency_seconds"], 0.28, places=2)
        self.assertEqual(summary["average_results_per_search"], 2.5)
        self.assertEqual(summary["search_fallback_count"], 1)

        # STRICT PRIVACY: Verify NO task queries, snippets, or URLs leaked in summary
        summary_str = str(summary)
        self.assertNotIn("search_query", summary)
        self.assertNotIn("search_results", summary)
        self.assertNotIn("Question 1?", summary_str)
        self.assertNotIn("Question 2?", summary_str)
        self.assertNotIn("Private Title 1", summary_str)
        self.assertNotIn("https://secret.org", summary_str)
        self.assertNotIn("Private snippet 1", summary_str)

        # Detailed per-task evaluation (private log) preserves details
        self.assertEqual(detailed[0]["search_query"], "Question 1?")
        self.assertEqual(detailed[0]["search_result_count"], 5)
        self.assertEqual(detailed[1]["search_fallback"], True)

    def test_v0_evaluation_and_scorer_remains_unchanged(self):
        tasks_by_id = {
            "v0-task-1": GAIATask("v0-task-1", "What is 100 + 50?", 1, "150"),
        }
        predictions = [
            {
                "task_id": "v0-task-1",
                "level": 1,
                "project_version": "v0",
                "final_answer": "150",
                "request_success": True,
                "completion_success": True,
                "latency_seconds": 1.5,
                "search_enabled": False,
            }
        ]

        metrics = calculate_metrics(
            predictions=predictions,
            tasks_by_id=tasks_by_id,
            level=1,
            project_version="v0",
        )

        summary = metrics["summary"]
        self.assertEqual(summary["project_version"], "v0")
        self.assertNotIn("search_enabled", summary)
        self.assertEqual(summary["accuracy"], 1.0)

        # Verify official scorer behaviors
        self.assertTrue(gaia_question_scorer("150", "150"))
        self.assertTrue(gaia_question_scorer("$1,500.00", "1500"))
        self.assertTrue(gaia_question_scorer("Paris", "paris"))
        self.assertFalse(gaia_question_scorer("London", "Paris"))


class TestCLIParsers(unittest.TestCase):
    """Verify --version is required in CLI entry points to prevent accidental version drift."""

    def test_run_level_requires_version_cli_arg(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "evaluation.run_level", "--level", "1"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required: --version", result.stderr)

    def test_run_one_requires_version_cli_arg(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "evaluation.run_one", "-i", "0"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required: --version", result.stderr)


if __name__ == "__main__":
    unittest.main()

