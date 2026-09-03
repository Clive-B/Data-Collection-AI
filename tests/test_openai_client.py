import io
import json
import unittest
from unittest.mock import patch

from telecom_ai.openai_client import OpenAIConfig, enrich_with_copilot, generate_copilot_answer


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _analysis(decision="release"):
    return {
        "answer": "MTN increased from 100 to 110.",
        "intent": "trend",
        "analysis_id": "abc123",
        "analysis": {
            "metric": "Voice subscriptions",
            "statistics": [{"operator": "MTN", "percent_change": 10.0}],
            "insights": ["MTN increased by 10%."],
            "limitations": ["Missing periods are not interpolated."],
        },
        "evidence": [
            {
                "operator": "MTN",
                "period": "2026-07",
                "metric": "Voice subscriptions",
                "displayed_value": "110",
                "source": "sample.xlsx :: Monthly!A1",
                "numeric_value": 110.0,
            }
        ],
        "governance": {
            "release_decision": decision,
            "release_class": "R-A",
            "uncertainty_class": "U1",
        },
    }


class OpenAIClientTest(unittest.TestCase):
    def setUp(self):
        self.config = OpenAIConfig(api_key="test-key", model="test-model")

    @patch("telecom_ai.openai_client.urllib.request.urlopen")
    def test_responses_api_is_server_side_stateless_and_grounded(self, urlopen):
        urlopen.return_value = _Response(
            {
                "id": "resp_123",
                "model": "test-model",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Grounded narrative."}],
                    }
                ],
            }
        )
        result = generate_copilot_answer("Show the trend", _analysis(), self.config)
        self.assertEqual(result["answer"], "Grounded narrative.")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertFalse(body["store"])
        self.assertEqual(body["model"], "test-model")
        self.assertIn("MTN increased from 100 to 110", body["input"])
        self.assertNotIn("numeric_value", body["input"])
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    @patch("telecom_ai.openai_client.urllib.request.urlopen")
    def test_governance_hold_never_calls_openai(self, urlopen):
        result = enrich_with_copilot("Change the live network", _analysis("escalate"), self.config)
        urlopen.assert_not_called()
        self.assertEqual(result["copilot"]["status"], "skipped_by_governance")
        self.assertEqual(result["governance"]["data_transfer"], "none_governance_hold")

    def test_missing_key_keeps_local_answer(self):
        result = enrich_with_copilot("Show the trend", _analysis(), OpenAIConfig(api_key=""))
        self.assertEqual(result["answer"], "MTN increased from 100 to 110.")
        self.assertEqual(result["copilot"]["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
