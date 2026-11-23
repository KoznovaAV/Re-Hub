"""Validate outgoing ParserResult against the shared JSON Schema."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / "contracts/parser-result.schema.json"
if not SCHEMA.exists():
    SCHEMA = Path("/app/contracts/parser-result.schema.json")
validator = Draft202012Validator(
    json.loads(SCHEMA.read_text(encoding="utf-8")),
    format_checker=FormatChecker(),
)
Draft202012Validator.check_schema(validator.schema)

def validate_result(result):
    validator.validate(result)
    return result
