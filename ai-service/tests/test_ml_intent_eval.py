from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import ml_intent_eval


class IntentEvalTest(unittest.TestCase):
    def test_metadata_uses_exact_model_tag(self):
        tags = {"models": [{"name": "qwen3:8b", "digest": "other"},
                           {"model": "qwen3:4b", "digest": "target"}]}
        with patch.object(ml_intent_eval, "urlopen", side_effect=[
            io.BytesIO(b'{"version":"0.40.16"}'), io.BytesIO(json.dumps(tags).encode()),
        ]):
            metadata = ml_intent_eval.provider_metadata("http://localhost", "qwen3:4b")
        self.assertEqual(metadata, {
            "ollama_version": "0.40.16", "model_digest": "target", "metadata_errors": [],
        })

    def test_report_excludes_warmup_and_provider_errors_from_median(self):
        expected = {"intent": "clarify", "period": None, "client_ref": None,
                    "min_unsent": None, "reason": "missing_period"}
        case = {"id": "TEST-1", "question": "Покажи должников", "category": "ambiguity", "expected": expected}
        metadata = {"ollama_version": "0.40.16", "model_digest": "target", "metadata_errors": []}
        with TemporaryDirectory() as temp:
            path = Path(temp) / "cases.jsonl"
            path.write_text(json.dumps(case) + "\n" + json.dumps(case | {"id": "TEST-2"}), encoding="utf-8")
            args = ["eval", str(path), "--warmup", "--require-ollama-version", "0.40.16"]
            with (
                patch("sys.argv", args),
                patch.object(ml_intent_eval, "provider_metadata", return_value=metadata),
                patch.object(ml_intent_eval, "timed_predict", side_effect=[
                    (expected, 3000), (expected, 50), ({"error": "provider failed"}, 1000),
                ]) as predict,
                redirect_stdout(io.StringIO()) as out,
            ):
                self.assertEqual(ml_intent_eval.main(), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(predict.call_count, 3)
            self.assertEqual(report["warmup"], {"latency_ms": 3000, "error": None})
            self.assertEqual(report["by_category"]["ambiguity"], {
                "passed": 1, "total": 2, "errors": 1, "median_latency_ms": 50,
            })
            self.assertEqual(len(report["metadata"]["prompt_sha256"]), 64)
            self.assertEqual(report["metadata"]["period_registry_version"], "1.0")

            with (
                patch("sys.argv", args[:-1] + ["0.40.15"]),
                patch.object(ml_intent_eval, "provider_metadata", return_value=metadata),
                patch.object(ml_intent_eval, "timed_predict") as predict,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                ml_intent_eval.main()
            self.assertEqual(error.exception.code, 2)
            predict.assert_not_called()
