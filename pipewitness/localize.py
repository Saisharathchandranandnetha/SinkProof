"""Static fault localisation from Collector configuration and contract findings."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from pydantic import BaseModel
from ruamel.yaml import YAML

yaml = YAML()


class LocalisationResult(BaseModel):
    pipeline_path: list[str] = []
    on_path_referencing_key: list[str] = []
    elsewhere_referencing_key: list[str] = []
    explanation: str = ""


def _processor_references_key(proc_def: Any, key: str) -> bool:
    """Check if processor definition mentions key or a key pattern matching it."""
    s = str(proc_def)
    if key in s:
        return True
    # Also check if base parts match e.g. "password" in user.password
    sub = key.split(".")[-1]
    if sub in s and len(sub) > 2:
        return True
    return False


def localize_fault(
    config_path: Path,
    sink_exporter: str,
    key: str,
) -> LocalisationResult:
    """Deterministically localize why a key/canary wasn't processed on the sink's pipeline."""
    cfg_data = yaml.load(config_path)
    pipelines = cfg_data.get("service", {}).get("pipelines", {})
    processors = cfg_data.get("processors", {})

    target_pipeline_id = None
    target_pipeline_spec = None

    for p_id, p_spec in pipelines.items():
        if sink_exporter in p_spec.get("exporters", []):
            target_pipeline_id = p_id
            target_pipeline_spec = p_spec
            break

    if not target_pipeline_id or not target_pipeline_spec:
        return LocalisationResult(explanation=f"Sink exporter {sink_exporter} not found in any pipeline")

    # Build pipeline path
    pipeline_path = []
    for r in target_pipeline_spec.get("receivers", []):
        pipeline_path.append(f"receiver:{r}")
    for p in target_pipeline_spec.get("processors", []):
        pipeline_path.append(f"processor:{p}")
    for e in target_pipeline_spec.get("exporters", []):
        pipeline_path.append(f"exporter:{e}")

    on_path_refs = []
    for p_name in target_pipeline_spec.get("processors", []):
        p_def = processors.get(p_name)
        if _processor_references_key(p_def, key):
            on_path_refs.append(f"{p_name} ({target_pipeline_id})")

    elsewhere_refs = []
    for p_id, p_spec in pipelines.items():
        if p_id == target_pipeline_id:
            continue
        for p_name in p_spec.get("processors", []):
            p_def = processors.get(p_name)
            if _processor_references_key(p_def, key):
                ref_str = f"{p_name} ({p_id})"
                if ref_str not in elsewhere_refs:
                    elsewhere_refs.append(ref_str)

    # Explanation
    if not on_path_refs and elsewhere_refs:
        explanation = (
            f"No processor on {target_pipeline_id} references {key}; "
            f"{', '.join(elsewhere_refs)} references it, but on a different pipeline."
        )
    elif not on_path_refs and not elsewhere_refs:
        explanation = f"No processor in the entire configuration references {key}."
    else:
        explanation = (
            f"Processor {', '.join(on_path_refs)} references {key} on {target_pipeline_id}, "
            f"but rule did not prevent the violation or deleted an invariant field."
        )

    return LocalisationResult(
        pipeline_path=pipeline_path,
        on_path_referencing_key=on_path_refs,
        elsewhere_referencing_key=elsewhere_refs,
        explanation=explanation,
    )
