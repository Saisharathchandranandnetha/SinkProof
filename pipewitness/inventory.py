"""Extract inventory deterministically from Collector config and telemetry fixtures."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel
from ruamel.yaml import YAML

from pipewitness.fixtures import FixtureSet, load_fixtures

yaml = YAML()


class PipelineInventory(BaseModel):
    id: str
    receivers: list[str] = []
    processors: list[str] = []
    exporters: list[str] = []


class ConfigInventory(BaseModel):
    sinks: list[str] = []  # exporter ids e.g. ["file/siem", "file/analytics"]
    pipelines: list[PipelineInventory] = []
    processors: dict[str, Any] = {}
    keys_referenced_by_processor: dict[str, list[str]] = {}
    fixture_keys_by_scope: dict[str, list[str]] = {}
    canary_names: list[str] = []


_KEY_EXTRACT_RE = re.compile(r'["\']([a-zA-Z0-9_\.]+)["\']')


def extract_keys_from_processor_config(proc_config: Any) -> list[str]:
    """Find attribute keys referenced in a processor configuration."""
    keys: set[str] = set()
    s = str(proc_config)
    for match in _KEY_EXTRACT_RE.findall(s):
        if "." in match or match in ("password", "token", "email", "id", "request_id", "trace_id"):
            keys.add(match)
    return sorted(keys)


def build_inventory(config_path: Path, telemetry: Path | FixtureSet) -> ConfigInventory:
    """Build deterministic inventory from config and fixtures."""
    fixtures = telemetry if isinstance(telemetry, FixtureSet) else load_fixtures(telemetry)
    cfg_data = yaml.load(config_path)

    # Exporters
    exporters = list(cfg_data.get("exporters", {}).keys())
    sinks: set[str] = set()
    for exp in exporters:
        sinks.add(exp)
        if "/" in exp:
            sinks.add(exp.split("/", 1)[1])

    # Pipelines
    pipelines_data = cfg_data.get("service", {}).get("pipelines", {})
    pipelines: list[PipelineInventory] = []
    for p_id, p_spec in pipelines_data.items():
        pipelines.append(PipelineInventory(
            id=p_id,
            receivers=list(p_spec.get("receivers", [])),
            processors=list(p_spec.get("processors", [])),
            exporters=list(p_spec.get("exporters", [])),
        ))

    # Processors
    procs = cfg_data.get("processors", {})
    keys_by_proc: dict[str, list[str]] = {}
    for proc_name, proc_def in procs.items():
        keys_by_proc[proc_name] = extract_keys_from_processor_config(proc_def)

    # Fixture keys by scope
    log_keys: set[str] = set()
    res_keys: set[str] = set()
    record_keys = ["body", "trace_id", "span_id", "severity_number"]
    for case in fixtures.cases:
        log_keys.update(case.attributes.keys())
        res_keys.update(case.resource.keys())

    return ConfigInventory(
        sinks=sorted(sinks),
        pipelines=pipelines,
        processors=procs,
        keys_referenced_by_processor=keys_by_proc,
        fixture_keys_by_scope={
            "log": sorted(log_keys),
            "resource": sorted(res_keys),
            "record": record_keys,
        },
        canary_names=[c.name for c in fixtures.canaries],
    )
