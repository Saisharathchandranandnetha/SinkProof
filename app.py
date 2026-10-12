"""SinkProof — Streamlit Interactive Web Application."""

from __future__ import annotations

import json
import os
from pathlib import Path

import streamlit as st
from PIL import Image

from pipewitness.ai.gemma import compile_contracts_with_gemma
from pipewitness.capture import parse_captures
from pipewitness.contracts import ContractSuite, load_contracts
from pipewitness.fixtures import load_fixtures
from pipewitness.mutate import run_mutations
from pipewitness.runner import get_image_digest, run_collector, validate_config
from pipewitness.verify import verify_suite

# Set page config
st.set_page_config(
    page_title="SinkProof — Telemetry Contract Testing",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for clean, high-contrast, serious platform UI
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .badge-live {
        background-color: #a6e3a1;
        color: #11111b;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .badge-recorded {
        background-color: #89b4fa;
        color: #11111b;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.85em;
    }
    .verdict-pass {
        color: #a6e3a1;
        font-weight: bold;
    }
    .verdict-fail {
        color: #f38ba8;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialise session state
if "compiled_suite" not in st.session_state:
    st.session_state.compiled_suite = None
if "gemma_mode" not in st.session_state:
    st.session_state.gemma_mode = "LIVE Gemma (or recorded fallback)"
if "verification_summary" not in st.session_state:
    st.session_state.verification_summary = None
if "selected_config_name" not in st.session_state:
    st.session_state.selected_config_name = "collector.vulnerable.yaml"
if "mutation_result_strong" not in st.session_state:
    st.session_state.mutation_result_strong = None
if "mutation_result_weak" not in st.session_state:
    st.session_state.mutation_result_weak = None

# Top Banner
collector_img = os.getenv("PW_COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:latest")
col_b1, col_b2 = st.columns([3, 1])
with col_b1:
    st.title("🛡️ SinkProof")
    st.caption("Executable contracts for telemetry pipelines — proven against a real OpenTelemetry Collector.")
with col_b2:
    st.markdown(f"""
    <div style="text-align: right; margin-top: 15px;">
        <span class="badge-recorded">AI: {st.session_state.gemma_mode}</span><br/>
        <span style="font-family: monospace; font-size: 0.8em; color: #888;">Collector: {collector_img}</span>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# Paths
base_dir = Path("examples/checkout")
diag_path = base_dir / "architecture.png"
req_path = base_dir / "requirements.txt"
telemetry_path = base_dir / "telemetry.yaml"
contracts_path = base_dir / "contracts.yaml"
contracts_weak_path = base_dir / "contracts.weak.yaml"
vulnerable_path = base_dir / "collector.vulnerable.yaml"
fixed_path = base_dir / "collector.fixed.yaml"

# ----------------- SECTION 1: INTENT & COMPILATION -----------------
st.header("1. Pipeline Intent & Gemma 4 Contract Compiler")
col_in1, col_in2 = st.columns([1, 1])

with col_in1:
    st.subheader("Architecture & Plain-English Requirements")
    if diag_path.exists():
        st.image(str(diag_path), caption="Target Observability Architecture", use_container_width=True)
    req_text = req_path.read_text() if req_path.exists() else ""
    st.text_area("Plain-English Requirement", value=req_text, height=90, disabled=True)

with col_in2:
    st.subheader("Compiled Telemetry Contracts")
    compile_clicked = st.button("✨ Compile with Gemma 4", type="primary", use_container_width=True)
    if compile_clicked:
        with st.spinner("Compiling contracts with Gemma 4..."):
            suite, mode_label, diff_str = compile_contracts_with_gemma(
                image_path=diag_path,
                requirements_path=req_path,
                config_path=vulnerable_path,
                telemetry_path=telemetry_path,
            )
            st.session_state.compiled_suite = suite
            st.session_state.gemma_mode = mode_label
            st.session_state.diff_str = diff_str
            st.success(f"Compiled {len(suite.contracts)} guarded contracts ({mode_label})")

    # Display active suite
    suite_to_show = st.session_state.compiled_suite or load_contracts(contracts_path)
    c_data = []
    for c in suite_to_show.contracts:
        quote = c.source.quote if c.source else "Human authored"
        c_data.append({
            "ID": c.id,
            "Type": c.type,
            "Severity": c.severity.upper(),
            "Sinks": ", ".join(c.get_target_sinks()),
            "Source Quote": quote,
            "Status": "✅ " + c.status,
        })
    st.dataframe(c_data, use_container_width=True, hide_index=True)
    if hasattr(st.session_state, "diff_str") and st.session_state.diff_str:
        st.info(st.session_state.diff_str)

st.divider()

# ----------------- SECTION 2: PIPELINE TOPOLOGY -----------------
st.header("2. Pipeline Topology")
summary = st.session_state.verification_summary
failed_path_red = False
failed_path_edges = []
if summary and summary.overall_verdict == "FAIL":
    failed_path_red = True

dot_graph = f"""
digraph G {{
    rankdir=LR;
    node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=10, fillcolor="#313244", fontcolor="#cdd6f4", color="#89b4fa"];
    edge [color="#cdd6f4", fontname="Helvetica", fontsize=9];

    subgraph cluster_sources {{
        label="Sources";
        style=dashed;
        color="#585b70";
        auth [label="Auth Service\\n(c1)", fillcolor="#45475a"];
        checkout [label="Checkout\\n(c2, c3)", fillcolor="#45475a"];
        payments [label="Payments\\n(c4)", fillcolor="#45475a"];
    }}

    subgraph cluster_collector {{
        label="OpenTelemetry Collector";
        style=solid;
        color="#a6e3a1";
        rx [label="receiver:otlp", fillcolor="#181825"];

        subgraph cluster_siem {{
            label="logs/siem";
            p_flt [label="filter/errors_only"];
            p_redact_siem [label="transform/redact\\n(Fixed only)"];
            p_batch1 [label="batch"];
        }}

        subgraph cluster_analytics {{
            label="logs/analytics";
            p_scrub [label="transform/scrub"];
            p_batch2 [label="batch"];
        }}
    }}

    subgraph cluster_sinks {{
        label="Sinks (Captured)";
        style=dashed;
        color="#f38ba8";
        sink_siem [label="SIEM (External)\\nfile/siem", fillcolor="#45475a"];
        sink_analytics [label="Analytics (External)\\nfile/analytics", fillcolor="#45475a"];
    }}

    auth -> rx;
    checkout -> rx;
    payments -> rx;

    rx -> p_flt [color="{'#f38ba8' if failed_path_red else '#cdd6f4'}", penwidth={"3" if failed_path_red else "1"}];
    p_flt -> p_batch1 [color="{'#f38ba8' if failed_path_red else '#cdd6f4'}", penwidth={"3" if failed_path_red else "1"}];
    p_batch1 -> sink_siem [color="{'#f38ba8' if failed_path_red else '#cdd6f4'}", penwidth={"3" if failed_path_red else "1"}];

    rx -> p_scrub;
    p_scrub -> p_batch2;
    p_batch2 -> sink_analytics;
}}
"""
st.graphviz_chart(dot_graph, use_container_width=True)
if failed_path_red:
    st.error("⚠️ Red edges highlight the failing pipeline path where secret/canary leaks occurred!")

st.divider()

# ----------------- SECTION 3: VERIFICATION -----------------
st.header("3. Pre-Deployment Verification (Real Collector)")
col_v1, col_v2 = st.columns([1, 2])

with col_v1:
    cfg_choice = st.radio(
        "Select Collector Configuration to Test:",
        ["collector.vulnerable.yaml", "collector.fixed.yaml"],
        index=0 if st.session_state.selected_config_name == "collector.vulnerable.yaml" else 1,
    )
    st.session_state.selected_config_name = cfg_choice
    active_cfg_path = vulnerable_path if cfg_choice == "collector.vulnerable.yaml" else fixed_path

    run_verify_btn = st.button("🚀 Run Verification", type="primary", use_container_width=True)
    if run_verify_btn:
        with st.spinner("Executing real otelcol-contrib container and verifying contracts..."):
            fixture_set = load_fixtures(telemetry_path)
            suite = st.session_state.compiled_suite or load_contracts(contracts_path)
            run_res = run_collector(active_cfg_path, fixture_set)
            if not run_res.success:
                st.error(f"Collector run failed: {run_res.error}")
            else:
                sink_map = {s_id: s_def.exporter for s_id, s_def in suite.sinks.items()}
                captures = parse_captures(run_res.captures_dir, sink_map)
                run_meta = {
                    "config_sha256": run_res.config_sha256,
                    "fixture_sha256": run_res.fixture_sha256,
                    "collector_image": run_res.image_digest or run_res.image,
                    "mode": "docker",
                }
                summary = verify_suite(suite, fixture_set, captures, active_cfg_path, run_meta)
                st.session_state.verification_summary = summary
                st.rerun()

with col_v2:
    if st.session_state.verification_summary:
        s = st.session_state.verification_summary
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("Overall Verdict", s.overall_verdict)
        m_c2.metric("Passed", f"{s.passed}/{s.total_contracts}")
        m_c3.metric("Failed", s.failed)
        m_c4.metric("Inconclusive", s.inconclusive)

        v_rows = []
        for ev in s.evidence_records:
            icon = "✅" if ev.verdict == "PASS" else ("❌" if ev.verdict == "FAIL" else "⚠️")
            v_rows.append({
                "Contract ID": ev.contract_id,
                "Verdict": f"{icon} {ev.verdict}",
                "Severity": ev.severity.upper(),
                "Sink": ev.sink,
                "Case": ev.case_id or "All",
            })
        st.dataframe(v_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Click 'Run Verification' to test the selected Collector config against the real container.")

st.divider()

# ----------------- SECTION 4: EVIDENCE & LOCALISATION -----------------
st.header("4. Evidence & Static Fault Localisation")
if st.session_state.verification_summary and st.session_state.verification_summary.failed > 0:
    failed_evs = [e for e in st.session_state.verification_summary.evidence_records if e.verdict == "FAIL"]
    selected_ev_id = st.selectbox(
        "Select Failure Evidence to Inspect:",
        [f"{e.contract_id} (case={e.case_id}, sink={e.sink}, canary={e.canary})" for e in failed_evs],
    )
    selected_ev = failed_evs[0]
    for e in failed_evs:
        if f"{e.contract_id} (case={e.case_id}, sink={e.sink}, canary={e.canary})" == selected_ev_id:
            selected_ev = e
            break

    e_c1, e_c2 = st.columns([1, 1])
    with e_c1:
        st.subheader("Canary / Field Findings")
        if selected_ev.input:
            st.markdown(f"**Input Value:** `[{selected_ev.input.scope}] {selected_ev.input.key} = {selected_ev.input.value}`")
        if selected_ev.observed:
            st.markdown(f"**Observed in Output:** `[{selected_ev.observed.scope}] {selected_ev.observed.key} = {selected_ev.observed.value}`")
        else:
            st.markdown(f"**Observed in Output:** `<MISSING / DELETED>`")
        st.markdown(f"**Pipeline Path:** `{' -> '.join(selected_ev.pipeline_path)}`")

    with e_c2:
        st.subheader("Static Fault Localisation")
        if selected_ev.localisation:
            st.info(f"📍 **Root Cause:** {selected_ev.localisation.explanation}")
            st.markdown(f"- **Processors on path referencing key:** `{selected_ev.localisation.on_path_referencing_key or 'None'}`")
            st.markdown(f"- **Processors elsewhere referencing key:** `{selected_ev.localisation.elsewhere_referencing_key or 'None'}`")

    st.code(json.dumps(selected_ev.model_dump(exclude_none=True), indent=2), language="json")
else:
    st.success("No active failure evidence. All contracts passed or verification not yet run.")

st.divider()

# ----------------- SECTION 5: MUTATION TESTING -----------------
st.header("5. Telemetry Mutation Engine & Test Adequacy")
st.caption("Proves whether your contracts actually catch regressions by introducing structure-aware mutations.")

col_m_btn, col_m_space = st.columns([1, 2])
with col_m_btn:
    run_mut_btn = st.button("🧬 Run Mutation Engine", type="primary", use_container_width=True)

if run_mut_btn:
    with st.spinner("Generating mutants and running real Collector executions..."):
        res_strong = run_mutations(fixed_path, contracts_path, telemetry_path, max_workers=4)
        res_weak = run_mutations(fixed_path, contracts_weak_path, telemetry_path, max_workers=4)
        st.session_state.mutation_result_strong = res_strong
        st.session_state.mutation_result_weak = res_weak
        st.rerun()

if st.session_state.mutation_result_strong and st.session_state.mutation_result_weak:
    rs = st.session_state.mutation_result_strong
    rw = st.session_state.mutation_result_weak

    score_col1, score_col2 = st.columns(2)
    with score_col1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Weak Contract Suite</h3>
            <p style="font-size: 2.2em; font-weight: bold; color: #f38ba8;">{rw.score:.1%}</p>
            <p>{rw.killed} killed / {rw.killed + rw.survived} evaluated (Only reachability checked)</p>
        </div>
        """, unsafe_allow_html=True)

    with score_col2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Strong Contract Suite</h3>
            <p style="font-size: 2.2em; font-weight: bold; color: #a6e3a1;">{rs.score:.1%}</p>
            <p>{rs.killed} killed / {rs.killed + rs.survived} evaluated (Full invariants checked)</p>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("Mutant Breakdown (Strong Suite)")
    m_table = []
    for m in rs.mutants:
        m_table.append({
            "ID": m.id,
            "Operator": m.operator,
            "Location": m.location,
            "Outcome": "🟢 KILLED" if m.outcome == "killed" else "🔴 SURVIVED",
            "Killed By": ", ".join(m.killed_by) if m.killed_by else "None (Survivor)",
        })
    st.dataframe(m_table, use_container_width=True, hide_index=True)
else:
    st.info("Click 'Run Mutation Engine' to benchmark the strong contracts vs weak contracts.")

st.divider()

# ----------------- SECTION 6: VERIFIED REMEDIATION (P1) -----------------
st.header("6. AI-Assisted Verified Remediation (P1)")
st.caption("Gemma proposes structured patch operations → applied in sandbox → verified against all contracts + mutations.")

col_fix1, col_fix2 = st.columns([1, 1])
with col_fix1:
    st.markdown("**Target Vulnerable Configuration:** `collector.vulnerable.yaml`")
    fix_btn = st.button("🔧 Propose & Verify Fix", type="primary", use_container_width=True)

if fix_btn:
    from pipewitness.ai.remediate import remediate_config
    with st.spinner("Applying structured patch ops and running sandbox verification..."):
        fixture_set = load_fixtures(telemetry_path)
        suite = load_contracts(contracts_path)
        run_res = run_collector(vulnerable_path, fixture_set)
        sink_map = {s_id: s_def.exporter for s_id, s_def in suite.sinks.items()}
        captures = parse_captures(run_res.captures_dir, sink_map)
        summary = verify_suite(suite, fixture_set, captures, vulnerable_path)
        rem_res = remediate_config(vulnerable_path, contracts_path, telemetry_path, summary)
        st.session_state.remediation_result = rem_res
        st.rerun()

if "remediation_result" in st.session_state and st.session_state.remediation_result:
    rr = st.session_state.remediation_result
    with col_fix2:
        if rr.status == "VERIFIED FIX":
            st.success(f"🎉 **{rr.status}**")
            st.markdown(f"**Verification:** Passed ✅ | **Mutation Score:** {rr.mutation_score:.1%}")
            st.markdown(f"*{rr.explanation}*")
        else:
            st.error(f"❌ **{rr.status}**: {rr.explanation}")

    st.subheader("Proposed Patch Operations")
    op_list = [op.model_dump(exclude_none=True) for op in rr.patch_ops]
    st.json(op_list)

    with st.expander("View Patched Configuration YAML"):
        st.code(rr.patched_yaml, language="yaml")
