# Project Name: SinkProof

> **Telemetry contract testing harness for OpenTelemetry Collector pipelines using Gemma 4 multimodal compilation and deterministic verification.**

---

## Team / Attendee Information

- **Primary Contact Name:** Saisharathchandranandnetha
- **GitHub Handle:** [@Saisharathchandranandnetha](https://github.com/Saisharathchandranandnetha)
- **Teammates:** Solo
- **Event:** NIAT-KKH × MLH Hack Day 2026 (Hyderabad)

---

## Challenge Selection

- [x] **Best Open-Source AI Project**
- [x] **Best Use of Gemma 4**

---

## Repository & License

- **Public Repository URL:** [https://github.com/Saisharathchandranandnetha/SinkProof](https://github.com/Saisharathchandranandnetha/SinkProof)
- **License:** Apache License 2.0 (OSI-approved)
- **Local Demo:** Run via `streamlit run app.py` (accessible at `http://localhost:8501`) or CLI `sinkproof verify --config examples/checkout/vulnerable.yaml --telemetry examples/checkout/fixtures.yaml --contracts examples/checkout/contracts.json`

---

## Short Pitch

SinkProof is an open-source contract-testing and mutation framework for OpenTelemetry Collector pipelines. It pairs **Gemma 4** (multimodal architecture ingestion + guarded contract compilation + OTTL patch remediation) with a **deterministic verifier** running a real isolated Collector binary, preventing silent telemetry drops, compliance stripping, and PII leaks before production deployment.

---

## The Problem

OpenTelemetry Collector pipelines route, redact, and transform mission-critical observability data across distributed architectures. However, today's observability pipelines have a critical blind spot:
1. **Silent Failures:** Filter processors, transforms, and routing statements often drop spans or strip sensitive attributes silently when misconfigured.
2. **Untested Compliance Guarantees:** PCI-DSS/HIPAA require redaction (e.g., masking `payment.card.number`), but pipeline configs are verified manually or not at all.
3. **No Non-Vacuous Verification:** In traditional unit tests, a sink that received zero data might pass an assertion like "no unmasked cards appeared in Datadog" simply because all telemetry was dropped.
4. **Configuration Drift:** When engineers update OTTL (OpenTelemetry Transformation Language) statements, regression testing is painful and error-prone.

---

## The Solution

SinkProof turns pipeline configs and architecture diagrams into automated, enforceable contracts:

1. **Multimodal Contract Compilation (Gemma 4):**
   - Ingests the architecture diagram PNG + requirement text.
   - Extracts semantic pipelines, sources, processors, and sinks.
   - Compiles structured **Contract IR** (Delivery, Redaction, Transform, and Cardinality contracts) with strict schema guardrails.

2. **Isolated Container Test Runner:**
   - Mounts candidate pipeline configurations into an isolated OpenTelemetry Collector container (`otel/opentelemetry-collector-contrib`).
   - Automatically injects test file-exporters into pipeline definitions without modifying original behavior.
   - Injects synthetic OTLP test payloads along with canary traces to guarantee data reaches each exporter.

3. **Deterministic Contract Verifier with Non-Vacuity Enforcement:**
   - Normalizes captured output traces into structured dictionaries.
   - Enforces **Non-Vacuity:** If a sink is empty, negative assertions (`must_not_contain`) fail instead of falsely passing.
   - Evaluates delivery, attribute presence, and PII redaction deterministically.

4. **Static Fault Localisation & Remediation Loop:**
   - Traces failed contracts through processor chains to identify the exact culprit processor.
   - Gemma 4 proposes pinpoint OTTL statements or YAML fixes.
   - Candidate patches are executed in a fresh test runner to guarantee the fix passes before presenting it to the engineer.

5. **Mutation Engine:**
   - Benchmarks contract suite robustness using 4 mutation operators (`drop_processor`, `drop_ottl_statement`, `perturb_key`, `weaken_filter`).
   - Weak test suites score low kill rates (~8%), while robust test suites achieve 100% kill rates.

---

## How Gemma 4 / AI is Used

1. **Vision-and-Text Contract Compilation:**
   - Gemma 4 analyzes architecture diagrams (e.g., checkout topology showing APM, Datadog, S3 cold storage) and textual security requirements.
   - Translates high-level compliance goals into machine-executable OTel contracts.

2. **Guarded Generation (`pipewitness/ai/guard.py`):**
   - All Gemma outputs are validated through a strict schema guard.
   - Disallows hallucinated sink names, unknown attribute keys, or unbound rules.
   - Requires every contract to quote an exact citation from the source architecture or spec.
   - Supports 1-shot self-repair if JSON formatting or schema violations occur.

3. **Autonomous Patch Remediation:**
   - When contracts fail, Gemma analyzes the static fault localization report and generates exact OTTL / YAML replacement patches.
   - Patches are deterministically re-verified through the container runner to prevent regressions.

4. **100% Open-Weights & Local Execution:**
   - Fully supports local inference via Ollama (`PW_BACKEND=ollama`, running local Gemma) with zero external dependency, or cloud inference via the Google GenAI SDK.
   - Transparent record-and-replay cache (`examples/checkout/recorded/`) guarantees offline determinism and reproducible evaluation.

---

## Approach and Technologies

- **Core Technologies:**
  - **Language:** Python 3.12+ (modern type hints, Pydantic dataclasses)
  - **Runner:** Docker (`otel/opentelemetry-collector-contrib` pinned container image)
  - **AI Engine:** Gemma 4 / Gemma 2 via Ollama (open-weights local inference) & Google GenAI API
  - **UI / Dashboard:** Streamlit (`app.py`) for visual contract evaluation, mutation analysis, and live logs
  - **Testing:** Pytest (21 unit and integration tests)
- **AI-Assisted Engineering Disclosure:**
  - Per Hack Day rules (§0 and §23), code scaffolding, test harnesses, and documentation were developed during the event. The primary product AI is Gemma 4, serving as the multimodal contract compiler and patch generator.

---

## Verification & Evidence

### 1. Test Suite Pass (21/21 Green)
```bash
$ pytest -v
============================== 21 passed in 0.46s ==============================
```

### 2. Contract Verification on Vulnerable vs. Fixed Pipelines
- **Vulnerable Pipeline (`examples/checkout/vulnerable.yaml`):**
  - **Verdict:** 4 PASS, 3 FAIL
  - **Failures Detected:**
    - `checkout-pii-redacted`: Unmasked credit card `payment.card.number` leaked into `datadog` and `s3_archive`.
    - `customer-tier-preserved`: Missing `customer.tier` attribute.
    - `service-version-delivery`: Stripped resource attribute.
- **Fixed Pipeline (`examples/checkout/fixed.yaml`):**
  - **Verdict:** 7 PASS, 0 FAIL (100% compliant)

### 3. Mutation Testing Benchmark
- **Weak Suite:** 1 / 12 mutants killed (**8.3% mutation score**).
- **Strong Suite:** 12 / 12 mutants killed (**100.0% mutation score**).
- Proves that the contracts are robust against subtle syntax and filter degradations.

---

## Demo / Reproduction Steps

### Option A: Interactive Web UI (Streamlit)
```bash
git clone https://github.com/Saisharathchandranandnetha/SinkProof.git
cd SinkProof
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
streamlit run app.py
```
Open `http://localhost:8501` to view:
1. **Contract Compiler Tab:** Multimodal Gemma 4 compilation of checkout architecture.
2. **Verify Tab:** Real OpenTelemetry Collector container run comparing Vulnerable vs. Fixed configs.
3. **Localize & Remediate Tab:** Culprit processor detection + automated OTTL patch.
4. **Mutation Testing Tab:** Mutant generation and kill rate scoreboards.

### Option B: Command-Line Interface
```bash
# Verify against OpenTelemetry Collector
sinkproof verify \
  --config examples/checkout/vulnerable.yaml \
  --telemetry examples/checkout/fixtures.yaml \
  --contracts examples/checkout/contracts.json

# Run Mutation Testing
sinkproof mutate \
  --config examples/checkout/fixed.yaml \
  --telemetry examples/checkout/fixtures.yaml \
  --contracts examples/checkout/contracts.json
```
