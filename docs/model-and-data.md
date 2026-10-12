# Model and Data Specification

## Gemma Model Details
- **Primary Model ID:** `gemma-4-26b-a4b-it` (set via `PW_GEMMA_MODEL`)
- **API Provider:** Google Gemini API (`google-genai` official SDK)
- **Role:** Proposes contracts and structured patch operations. **Never decides verdicts or executes code.**

## Integration Locations
- **Contract Compiler:** `pipewitness/ai/gemma.py` -> `compile_contracts_with_gemma()` and `_call_gemini_api()`
- **Schema & Allow-List Guard:** `pipewitness/ai/guard.py` -> `guard_compiler_output()`
- **Prompt Definitions:** `pipewitness/ai/prompts.py`
  - `PROMPT_VERSION`: `"2026-10-12.v1"`
- **Deterministic Verifier:** `pipewitness/verify.py` -> `verify_suite()`
- **Mutation Engine:** `pipewitness/mutate.py` -> `run_mutations()`

## Record / Replay Specification
- **Directory:** `examples/checkout/recorded/`
- **Replay Key:** SHA256 of `(architecture.png + requirements.txt + inventory.json)`
- **Behavior:**
  - When live API credentials are present and reachable: executes live call, validates through guard, saves record.
  - When offline or without API key: replays cached response with identical input hash, labeled `RECORDED`.

## Synthetic Data & Canaries
All secrets and PII used in fixtures and tests are entirely synthetic:
- `password`: `PW_CANARY_7f3a91`
- `token`: `TOKEN_CANARY_b81c42`
- `email`: `canary.user@pipewitness.invalid`
No real customer data, credentials, or production telemetry is ever stored or processed.
