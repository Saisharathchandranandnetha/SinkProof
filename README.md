# SinkProof

> **Executable contracts for telemetry pipelines — proven against a real OpenTelemetry Collector, with mutation testing to prove the tests work.**

*Built during the event with AI coding assistants (Antigravity + Claude Code); the AI component of the product is Gemma 4.*

---

## 1. Problem

Platform and SRE teams write complex OpenTelemetry Collector YAML pipelines. When configs change, teams rely on eyeball reviews or "it starts without syntax errors."
Nobody verifies before deployment that:
- Secrets and PII never reach external exporters (e.g. SIEM or analytics).
- Critical fields other teams rely on (`request.id`, `trace_id`) survive every transformation.
- The right records reach the right destination and noise is filtered out.
- The verification tests would actually catch a regression if someone made a typo or deleted a redaction block.

**SinkProof solves this with three primitives:**
1. **Telemetry Contract IR:** A declarative YAML format of machine-checkable invariants over pipeline output verified deterministically against captured output of a **real** OpenTelemetry Collector run.
2. **Telemetry Mutation Engine & Mutation Score:** Structure-aware mutations of the Collector config to prove test suite adequacy (`Score = killed / (killed + survived)`).
3. **Static Fault Localisation:** When a contract fails, SinkProof pinpoints the pipeline path and identifies which processors do or do not reference the offending key.

---

## 2. Real Verification Output (From Today's Runs)

### On Vulnerable Config (`collector.vulnerable.yaml`)
```
PIPEWITNESS verifying examples/checkout/collector.vulnerable.yaml with examples/checkout/contracts.yaml...
                Verification Results (collector.vulnerable.yaml)                
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Contract ID         ┃ Type            ┃ Severity ┃ Verdict ┃ Details           ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ no-secret-canaries  │ forbidden_value │ critical │  FAIL   │ Leaked 'password' │
│                     │                 │          │         │ in c1 (siem);     │
│                     │                 │          │         │ Leaked 'token' in │
│                     │                 │          │         │ c1 (siem)         │
│ no-email-export     │ forbidden_value │ high     │  FAIL   │ Leaked 'email' in │
│                     │                 │          │         │ c1 (siem); Leaked │
│                     │                 │          │         │ 'email' in c4     │
│                     │                 │          │         │ (siem); Leaked    │
│                     │                 │          │         │ 'email' in c1     │
│                     │                 │          │         │ (analytics);      │
│                     │                 │          │         │ Leaked 'email' in │
│                     │                 │          │         │ c4 (analytics)    │
│ errors-reach-siem   │ must_reach      │ high     │  PASS   │ All invariants    │
│                     │                 │          │         │ preserved         │
│ debug-not-in-siem   │ must_not_reach  │ medium   │  PASS   │ All invariants    │
│                     │                 │          │         │ preserved         │
│ request-id-survives │ preserve_field  │ high     │  FAIL   │ Missing           │
│                     │                 │          │         │ 'request.id' in   │
│                     │                 │          │         │ c1 (analytics);   │
│                     │                 │          │         │ Missing           │
│                     │                 │          │         │ 'request.id' in   │
│                     │                 │          │         │ c2 (analytics);   │
│                     │                 │          │         │ Missing           │
│                     │                 │          │         │ 'request.id' in   │
│                     │                 │          │         │ c4 (analytics)    │
│ all-reach-analytics │ must_reach      │ medium   │  PASS   │ All invariants    │
│                     │                 │          │         │ preserved         │
│ trace-correlation-… │ preserve_field  │ medium   │  PASS   │ All invariants    │
│                     │                 │          │         │ preserved         │
└─────────────────────┴─────────────────┴──────────┴─────────┴───────────────────┘
Overall: FAIL (4 PASS, 3 FAIL, 0 INCONCLUSIVE)
Exit code: 1
```

### On Fixed Config (`collector.fixed.yaml`)
```
                  Verification Results (collector.fixed.yaml)                   
┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Contract ID         ┃ Type            ┃ Severity ┃ Verdict ┃ Details           ┃
┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ no-secret-canaries  │ forbidden_value │ critical │  PASS   │ All invariants    │
│ no-email-export     │ forbidden_value │ high     │  PASS   │ All invariants    │
│ errors-reach-siem   │ must_reach      │ high     │  PASS   │ All invariants    │
│ debug-not-in-siem   │ must_not_reach  │ medium   │  PASS   │ All invariants    │
│ request-id-survives │ preserve_field  │ high     │  PASS   │ All invariants    │
│ all-reach-analytics │ must_reach      │ medium   │  PASS   │ All invariants    │
│ trace-correlation-… │ preserve_field  │ medium   │  PASS   │ All invariants    │
└─────────────────────┴─────────────────┴──────────┴─────────┴───────────────────┘
Overall: PASS (7 PASS, 0 FAIL, 0 INCONCLUSIVE)
Exit code: 0
```

---

## 3. Telemetry Mutation Score (Test Adequacy)

Running mutation testing on `collector.fixed.yaml` with 4 operators (`drop_processor`, `drop_ottl_statement`, `perturb_key`, `weaken_filter`):

- **Weak Suite (`contracts.weak.yaml`):** Only checks reachability (`errors-reach-siem`, `all-reach-analytics`).
  - Score: **8.3%** (1 killed / 12 evaluated). 11 mutants survived undetected!
- **Strong Suite (`contracts.yaml`):** Full invariants suite.
  - Score: **100.0%** (12 killed / 12 evaluated). All 12 mutants detected and killed!

---

## 4. Gemma 4 Integration

- **Model:** `gemma-4-26b-a4b-it` via Google Gemini API (`google-genai` SDK).
- **Hard Rule:** AI **proposes, never judges**. Only `pipewitness/verify.py` produces verdicts.
- **Contract Compiler (`pipewitness/ai/gemma.py`):** Reads an architecture diagram (`architecture.png`) + plain-English requirement (`requirements.txt`) and extracts invariants.
- **Schema Guard (`pipewitness/ai/guard.py`):** Strips markdown fences, parses JSON, validates Pydantic models, and restricts values to strictly allow-listed inventories (sinks, fixture keys, canaries).
- **Record / Replay:** Every live model response is hashed and cached under `examples/checkout/recorded/<input_sha>.json` for offline reproducibility.

---

## 5. Quick Start

### Prerequisites
- Docker (with access to `otel/opentelemetry-collector-contrib`)
- Python 3.11+

### Installation
```bash
git clone https://github.com/netha/pipewitness.git
cd pipewitness
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configuration
```bash
cp .env.example .env
# Optional: add GEMINI_API_KEY for live Gemma calls (record/replay is enabled by default)
```

### Running Commands
```bash
# Verify vulnerable config (reproduces 4 PASS, 3 FAIL)
sinkproof verify -c examples/checkout/collector.vulnerable.yaml -k examples/checkout/contracts.yaml -t examples/checkout/telemetry.yaml

# Verify fixed config (reproduces 7 PASS, 0 FAIL)
sinkproof verify -c examples/checkout/collector.fixed.yaml -k examples/checkout/contracts.yaml -t examples/checkout/telemetry.yaml

# Run mutation testing (100% kill score on strong suite)
sinkproof mutate -c examples/checkout/collector.fixed.yaml -k examples/checkout/contracts.yaml -t examples/checkout/telemetry.yaml

# Compile contracts with Gemma 4
sinkproof compile -i examples/checkout/architecture.png -r examples/checkout/requirements.txt -c examples/checkout/collector.fixed.yaml -t examples/checkout/telemetry.yaml -o compiled.yaml

# Run end-to-end demo
sinkproof demo

# Launch Streamlit UI
streamlit run app.py
```

---

## 6. Submission Links & Architecture Map

| Subsystem | File Path | Primary Function |
|---|---|---|
| **Gemma 4 Integration** | `pipewitness/ai/gemma.py` | `compile_contracts_with_gemma()` |
| **Model Output Guard** | `pipewitness/ai/guard.py` | `guard_compiler_output()` |
| **Deterministic Verifier** | `pipewitness/verify.py` | `verify_suite()` |
| **Mutation Testing Engine** | `pipewitness/mutate.py` | `run_mutations()` |
| **Collector Runner** | `pipewitness/runner.py` | `run_collector()` |
| **Static Fault Localisation** | `pipewitness/localize.py` | `localize_fault()` |

---

## 7. Limitations & Scope

- **Signal types:** Log telemetry via OTLP/HTTP. Trace and metrics contracts are planned post-event.
- **Capture mechanism:** Uses file exporter capture within the container to safely intercept output without external mock network dependencies.
- **Data safety:** 100% synthetic canaries. No real customer or production credentials.

---

## 8. License

Licensed under the [Apache License, Version 2.0](LICENSE).
