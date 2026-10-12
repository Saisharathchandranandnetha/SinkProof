"""Model-output guard (spec §13.1): fences stripped → json → Pydantic → allow-lists → max 12.

No model calls: the guard is tested on raw response strings.

ASSUMED interfaces (fix only `check()` below if the real names differ):
  inventory.build_inventory(config_path, telemetry_path) -> inventory
  ai.guard.validate_response(raw_text, inventory) -> accepted contracts (list, or object with .contracts)
  rejection raises ValueError (pydantic.ValidationError and json.JSONDecodeError are both ValueErrors).
A wrong signature raises TypeError, which these tests do NOT count as a rejection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from pipewitness.ai.guard import validate_response
    from pipewitness.inventory import build_inventory

    _MISSING = None
except ImportError as e:
    _MISSING = e

pytestmark = pytest.mark.xfail(_MISSING is not None, reason=f"guard not built yet: {_MISSING}", strict=False)

CHECKOUT = Path(__file__).resolve().parents[1] / "examples" / "checkout"
SRC = {"kind": "text", "quote": "Passwords and tokens must never leave the collector"}


def contract(**kw) -> dict:
    return {"id": "no-secrets", "type": "forbidden_value", "sinks": ["siem", "analytics"],
            "canaries": ["password", "token"], "severity": "critical",
            "source": SRC, "status": "ready", **kw}


def preserve(**kw) -> dict:
    return {"id": "request-id", "type": "preserve_field", "sink": "analytics",
            "field": {"scope": "log", "key": "request.id"}, "severity": "high",
            "source": {"kind": "diagram", "quote": "keep request.id"}, "status": "ready", **kw}


def response(*contracts, **top) -> str:
    return json.dumps({"contracts": list(contracts), "unresolved": [], **top})


def check(raw: str) -> list[str]:
    inv = build_inventory(CHECKOUT / "collector.vulnerable.yaml", CHECKOUT / "telemetry.yaml")
    result = validate_response(raw, inv)
    return [c.id for c in getattr(result, "contracts", result)]


def test_valid_response_accepted():
    assert check(response(contract(), preserve())) == ["no-secrets", "request-id"]


@pytest.mark.parametrize("fence", ["```json\n{}\n```", "```\n{}\n```"])
def test_code_fences_are_stripped_then_accepted(fence):
    # Spec §13.1: the guard strips fences; fenced valid JSON is accepted, not rejected.
    assert check(fence.replace("{}", response(contract()))) == ["no-secrets"]


@pytest.mark.parametrize("raw", [
    "Sure! Here are your contracts.",
    response(contract(sinks=["siem", "datadog"])),                               # unknown sink
    response(preserve(sink="datadog")),                                           # unknown sink (single)
    response(preserve(field={"scope": "log", "key": "session.id"})),              # unknown key
    response(preserve(field={"scope": "galaxy", "key": "request.id"})),           # unknown scope
    response({"id": "sel", "type": "must_reach", "sink": "siem", "severity": "low",
              "when": {"has_attribute": {"scope": "log", "key": "ssn"}},
              "source": SRC, "status": "ready"}),                                 # unknown key in selector
    response(contract(canaries=["password", "ssn"])),                             # unknown canary
    response(contract(type="must_encrypt")),                                      # unknown contract type
    response(contract(confidence=0.97)),                                          # extra field on contract
    response(contract(), verdict="PASS"),                                         # extra top-level field
    response({k: v for k, v in contract().items() if k != "source"}),             # missing source
    response(contract(source={"kind": "guess", "quote": "x"})),                   # bad source kind
    response(contract(status="approved")),                                        # bad status
    response(contract(), contract()),                                             # duplicate ids
], ids=["prose", "unknown-sink", "unknown-sink-single", "unknown-key", "unknown-scope",
        "unknown-selector-key", "unknown-canary", "unknown-type", "extra-field", "extra-top-level",
        "missing-source", "bad-source-kind", "bad-status", "duplicate-ids"])
def test_rejected(raw):
    with pytest.raises(ValueError):
        check(raw)


def _n_contracts(n: int) -> str:
    return response(*(contract(id=f"c-{i}") for i in range(n)))


def test_twelve_contracts_accepted():
    assert len(check(_n_contracts(12))) == 12


def test_more_than_twelve_contracts_rejected():
    with pytest.raises(ValueError):
        check(_n_contracts(13))
