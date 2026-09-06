import unittest
from agent.agent import GAIAAgent, AgentResult
from agent.llm import LLMResponse
from prompts.baseline import build_baseline_prompt, BASELINE_SYSTEM_PROMPT, PROMPT_VERSION


class MockLLMClient:
    """Mock LLM client that returns LLMResponse and records prompt."""

    def __init__(
        self,
        response_text: str = "42",
        finish_reason: str = "STOP",
        input_tokens: int = 10,
        output_tokens: int = 2,
        thinking_tokens: int = 50,
        total_tokens: int = 62,
    ):
        self.response = LLMResponse(
            text=response_text,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            total_tokens=total_tokens,
            response_id="mock-resp-id",
            model_version="gemini-3.5-flash",
        )
        self.last_prompt = None

    def generate(self, prompt: str) -> LLMResponse:
        self.last_prompt = prompt
        return self.response


class TestGAIAAgent(unittest.TestCase):
    def test_prompt_construction(self):
        llm = MockLLMClient(response_text="Answer")
        agent = GAIAAgent(llm_client=llm)
        question = "What is the capital of France?"
        prompt = agent.build_prompt(question)

        self.assertIn(BASELINE_SYSTEM_PROMPT.strip(), prompt)
        self.assertIn(question, prompt)

    def test_run_preserves_raw_and_cleaned_separately(self):
        llm = MockLLMClient(response_text="  FINAL ANSWER: Paris  \n", finish_reason="STOP")
        agent = GAIAAgent(llm_client=llm)
        result = agent.run("What is the capital of France?")

        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.raw_response, "  FINAL ANSWER: Paris  \n")
        self.assertEqual(result.final_answer, "Paris")
        self.assertEqual(result.prompt_version, PROMPT_VERSION)
        self.assertIsNotNone(result.llm_response)
        self.assertEqual(result.llm_response.finish_reason, "STOP")
        self.assertEqual(result.llm_response.thinking_tokens, 50)
        self.assertEqual(result.llm_response.input_tokens, 10)
        self.assertEqual(result.llm_response.output_tokens, 2)
        self.assertEqual(result.llm_response.total_tokens, 62)

    def test_whitespace_cleaning(self):
        llm = MockLLMClient(response_text="   \n\t Berlin \n  ")
        agent = GAIAAgent(llm_client=llm)
        result = agent.run("What is the capital of Germany?")

        self.assertEqual(result.final_answer, "Berlin")

    def test_final_answer_prefix_cleaning(self):
        test_cases = [
            ("FINAL ANSWER: 42", "42"),
            ("Final Answer: 42", "42"),
            ("final answer: 42", "42"),
            ("Answer: 42", "42"),
            ("ANSWER: 42", "42"),
            ("FINAL ANSWER:   Rome  ", "Rome"),
        ]
        agent = GAIAAgent(llm_client=MockLLMClient())
        for raw, expected in test_cases:
            cleaned = agent.clean_answer(raw)
            self.assertEqual(cleaned, expected)

    def test_conservative_cleaning_preserves_content(self):
        raw = "The answer is 12,345.67 (exact)."
        agent = GAIAAgent(llm_client=MockLLMClient())
        cleaned = agent.clean_answer(raw)
        self.assertEqual(cleaned, raw)

    def test_callable_interface_returns_final_answer(self):
        llm = MockLLMClient(response_text="FINAL ANSWER: Tokyo")
        agent = GAIAAgent(llm_client=llm)
        self.assertEqual(agent("Capital of Japan?"), "Tokyo")


if __name__ == "__main__":
    unittest.main()
