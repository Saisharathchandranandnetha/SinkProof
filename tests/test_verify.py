"""Unit tests for Contract IR verification semantics and non-vacuity."""

from pathlib import Path
import pytest

from pipewitness.capture import NormalizedRecord
from pipewitness.contracts import ContractSuite, load_contracts
from pipewitness.fixtures import load_fixtures
from pipewitness.verify import verify_suite


@pytest.fixture
def fixtures():
    return load_fixtures(Path("examples/checkout/telemetry.yaml"))


@pytest.fixture
def contracts():
    return load_contracts(Path("examples/checkout/contracts.yaml"))


def test_hand_crafted_leak_detection(fixtures, contracts):
    # Simulated capture with leaked password
    leak_record = NormalizedRecord(
        sink="siem",
        exporter="file/siem",
        case_id="c1",
        severity_number=17,
        body="[pw:c1] test body",
        log_attrs={"user.password": "PW_CANARY_7f3a91", "pipewitness.case": "c1"},
    )
    summary = verify_suite(
        contracts,
        fixtures,
        [leak_record],
        Path("examples/checkout/collector.vulnerable.yaml"),
    )
    # no-secret-canaries should fail
    sec_ev = [e for e in summary.evidence_records if e.contract_id == "no-secret-canaries"]
    assert len(sec_ev) > 0
    assert sec_ev[0].verdict == "FAIL"
    assert sec_ev[0].canary == "password"


def test_non_vacuity_on_empty_sink(fixtures, contracts):
    # If no records reach siem at all, forbidden_value is INCONCLUSIVE, not PASS
    empty_records = [
        NormalizedRecord(
            sink="analytics",
            exporter="file/analytics",
            case_id="c2",
            severity_number=9,
            body="[pw:c2] checkout ok",
            log_attrs={"pipewitness.case": "c2", "request.id": "req-c2"},
        )
    ]
    summary = verify_suite(
        contracts,
        fixtures,
        empty_records,
        Path("examples/checkout/collector.fixed.yaml"),
    )
    # no-secret-canaries on siem had no carrying cases reach siem -> inconclusive
    sec_ev = [e for e in summary.evidence_records if e.contract_id == "no-secret-canaries"]
    assert any(e.verdict == "INCONCLUSIVE" for e in sec_ev)
