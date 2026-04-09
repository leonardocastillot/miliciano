# Miliciano 0.3.0 Orchestration Core Implementation Plan

> For Hermes: use subagent-driven-development to execute this plan task-by-task.

Goal: Convert Miliciano from a set of useful commands into a single orchestrated partner where Hermes is the brain/orchestrator, OpenClaw is execution, Ollama is local fast path, and Nemoclaw becomes the secure external/policy boundary.

Architecture: Keep Miliciano as the only user-facing interface. Introduce a central orchestration layer that classifies user intent, selects the correct subsystem, applies policy gates before execution, and verifies execution results before closing the loop. Preserve existing commands (`think`, `exec`, `mission`) as compatibility wrappers over the new orchestration core.

Tech Stack: Python CLI under `miliciano-poc/bin`, Hermes CLI, OpenClaw CLI, Nemoclaw CLI, Ollama local runtime, JSON state files, markdown docs.

---

## Current Codebase Facts

Existing entrypoints and responsibilities:
- `miliciano-poc/bin/miliciano` dispatches CLI subcommands.
- `miliciano-poc/bin/miliciano_exec.py` contains the current chat/query/exec/mission logic.
- `miliciano-poc/bin/miliciano_runtime.py` contains shared runtime helpers, routing, model state, fallback logic, and command runners.
- `miliciano-poc/bin/miliciano_controls.py` owns route/model/provider/auth management.
- `miliciano-poc/bin/miliciano_status.py` renders operational state.
- `miliciano-poc/bin/miliciano_setup.py` owns install/bootstrap/setup/doctor flows.

Important current gaps:
- There is no central `ask` or orchestration flow.
- Hermes plans, but does not yet run a full classify -> execute -> verify loop.
- Nemoclaw is installed/visible but not integrated into runtime orchestration.
- Policy is observational, not a real decision gate.
- `think`, `exec`, and `mission` are separate modes instead of a unified partner flow.

---

## Release Scope

This plan targets version `0.3.0` with these deliverables:
- New unified command: `miliciano ask "..."`
- Central orchestration engine
- Intent classification into reasoning / execution / hybrid / external / blocked
- Policy gate before execution
- Verify loop after execution
- Compatibility wrappers so old commands still work
- Status visibility for orchestration readiness
- Initial Nemoclaw integration stub for boundary/external tasks

Out of scope for 0.3.0:
- Full autonomous outward agent lifecycle through Nemoclaw
- Deep semantic learning pipeline
- Multi-tenant remote gateway architecture
- Full test suite migration if the repo currently lacks formal tests

---

## Task 1: Create orchestration design doc in repo

Objective: Capture the subsystem contract in-repo before code changes.

Files:
- Create: `docs/plans/2026-04-08-miliciano-v0.3.0-orchestration-core.md`
- Modify: none
- Test: none

Step 1: Ensure this plan file exists in `docs/plans/`.

Step 2: Keep the subsystem contract explicit:
- Miliciano = interface + installer + integrator
- Hermes = brain + memory + orchestrator
- OpenClaw = execution hands
- Ollama = local/fast reflex path
- Nemoclaw = secure boundary / external services layer

Step 3: Commit:
```bash
git add docs/plans/2026-04-08-miliciano-v0.3.0-orchestration-core.md
git commit -m "docs: add Miliciano 0.3.0 orchestration plan"
```

---

## Task 2: Add orchestration state helpers

Objective: Introduce shared structures for decisions, policies, and execution reports.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Test: temporary CLI smoke checks

Step 1: Add minimal helper builders in `miliciano_runtime.py`:
- `build_orchestration_decision(...)`
- `build_policy_result(...)`
- `build_execution_report(...)`

Use plain dicts first; avoid premature abstraction.

Suggested structure:
```python
def build_orchestration_decision(intent, target, reason, needs_execution=False, needs_policy=False, needs_external=False):
    return {
        "intent": intent,
        "target": target,
        "reason": reason,
        "needs_execution": needs_execution,
        "needs_policy": needs_policy,
        "needs_external": needs_external,
    }
```

Step 2: Add policy classification helpers:
- `detect_sensitive_action(prompt)`
- `detect_externalization_intent(prompt)`
- `classify_orchestration_intent(prompt)`

Initial intent buckets:
- `reasoning`
- `execution`
- `hybrid`
- `external`
- `blocked`

Step 3: Keep heuristics explicit and inspectable.

Step 4: Run validation:
```bash
python3 -m compileall miliciano-poc/bin
```
Expected: compile succeeds.

Step 5: Commit.

---

## Task 3: Create a real policy gate

Objective: Prevent the executor from being called blindly.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_status.py`

Step 1: Add `evaluate_policy_for_prompt(prompt, decision)` in `miliciano_runtime.py`.

Minimum outputs:
- `allow`
- `ask`
- `deny`

Initial triggers for `ask`:
- mentions `sudo`
- deleting files
- credential manipulation
- public exposure / webhooks / publish / deploy outward

Initial triggers for `deny`:
- clearly destructive or ambiguous dangerous commands without enough context

Step 2: Do not yet block the current shell globally; just return structured verdicts.

Step 3: Extend status output with a line like:
- `orchestration policy [ready|pending]`

Step 4: Run:
```bash
python3 -m compileall miliciano-poc/bin
./bin/miliciano.js status
```
Expected: status still renders cleanly.

Step 5: Commit.

---

## Task 4: Introduce central orchestration flow

Objective: Create one code path that Miliciano can use for “ask”.

Files:
- Modify: `miliciano-poc/bin/miliciano_exec.py`
- Modify: `miliciano-poc/bin/miliciano_runtime.py`

Step 1: Add a new function in `miliciano_exec.py`:
- `orchestrate_partner_request(prompt, session_id=None, force_mode=None)`

The flow should be:
1. classify intent
2. evaluate policy
3. route to Hermes / OpenClaw / local / Nemoclaw-stub
4. collect result
5. verify result
6. persist memory/trace

Step 2: Initial target mapping:
- reasoning -> Hermes or local fast route
- execution -> Hermes plans briefly, OpenClaw executes
- hybrid -> Hermes plans, OpenClaw executes, Hermes verifies
- external -> Hermes plans, Nemoclaw stub handles boundary decision, return “external path pending implementation” if not yet fully supported
- blocked -> return safe refusal / clarification-needed message

Step 3: Build verification using Hermes first:
- `verify_execution_result(prompt, result_text)`
- return a compact verdict: `passed`, `needs_followup`, `failed`

Step 4: Reuse `save_obsidian_memory(...)` so orchestration traces are not lost.

Step 5: Run smoke validation:
```bash
python3 -m compileall miliciano-poc/bin
./bin/miliciano.js think "resume el objetivo de este sistema"
./bin/miliciano.js exec "responde solo OK"
./bin/miliciano.js mission "explica la división reasoning vs execution"
```
Expected: old commands still work.

Step 6: Commit.

---

## Task 5: Add `miliciano ask`

Objective: Make Miliciano feel like one partner instead of many subcommands.

Files:
- Modify: `miliciano-poc/bin/miliciano`
- Modify: `miliciano-poc/bin/miliciano_exec.py`
- Modify: `miliciano-poc/bin/miliciano_ui.py`
- Modify: `README.md`

Step 1: Add CLI dispatch for:
```python
if sub == "ask":
    cmd_ask(arg)
    return
```

Step 2: Implement `cmd_ask(prompt)` to call `orchestrate_partner_request(...)`.

Step 3: Update interactive shell so the default chat path uses orchestration rather than directly calling `call_hermes_query(...)`.

Step 4: Keep `/fast` and `/reasoning` as overrides, but route them through orchestration.

Step 5: Update help text and README with:
- `miliciano ask "..."`
- “Miliciano is the single interface; Hermes/OpenClaw/Nemoclaw are internal organs.”

Step 6: Validation:
```bash
./bin/miliciano.js --help
./bin/miliciano.js ask "resume en una línea cómo operas"
```
Expected: help shows `ask`; command returns a coherent orchestrated answer.

Step 7: Commit.

---

## Task 6: Make old commands thin wrappers

Objective: Keep backward compatibility while centralizing orchestration.

Files:
- Modify: `miliciano-poc/bin/miliciano_exec.py`

Step 1: Refactor:
- `cmd_think` -> wrapper over orchestration with force mode `reasoning`
- `cmd_exec` -> wrapper over orchestration with force mode `execution`
- `cmd_mission` -> wrapper over orchestration with force mode `hybrid`

Step 2: Preserve output style, but stop duplicating planning/execution logic in several places.

Step 3: Validation:
```bash
./bin/miliciano.js think "qué eres"
./bin/miliciano.js exec "responde en una línea"
./bin/miliciano.js mission "explica tu flujo"
```
Expected: all work through the same internal orchestrator.

Step 4: Commit.

---

## Task 7: Add first-class Nemoclaw runtime stub

Objective: Stop treating Nemoclaw as mere “reserved model”.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_controls.py`
- Modify: `miliciano-poc/bin/miliciano_status.py`
- Modify: `README.md`

Step 1: Add minimal helper:
- `run_nemoclaw_boundary_action(prompt, decision)`

For 0.3.0 this can be a stub with explicit behavior:
- if external task detected and Nemoclaw is present, return structured “boundary acknowledged / outward path reserved” result
- if not present, return “pending Nemoclaw integration” result

Step 2: Update status/model/provider output so it no longer says Nemoclaw is only “reserved”; instead say:
- `boundary/external layer: stub integrated`
or
- `boundary/external layer: pending`

Step 3: Validation:
```bash
./bin/miliciano.js status
./bin/miliciano.js ask "quiero exponer un servicio externo seguro"
```
Expected: Miliciano recognizes the outward/boundary path explicitly.

Step 4: Commit.

---

## Task 8: Improve observability for orchestration

Objective: Make runtime decisions inspectable.

Files:
- Modify: `miliciano-poc/bin/miliciano_status.py`
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Optional: create `~/.config/miliciano/orchestration-report.json`

Step 1: Save the last orchestration decision/report to a JSON file.

Suggested file:
- `~/.config/miliciano/orchestration-report.json`

Step 2: Add a `status` section showing:
- orchestration mode
- last intent
- last target
- last policy verdict
- last verification verdict

Step 3: Validation:
```bash
./bin/miliciano.js ask "resume tu stack"
./bin/miliciano.js status
```
Expected: status exposes the latest orchestration trace.

Step 4: Commit.

---

## Task 9: Final release prep for 0.3.0

Objective: Make the release shippable.

Files:
- Modify: `README.md`
- Modify: `package.json`
- Optional: create `docs/releases/v0.3.0.md`

Step 1: Bump version from `0.2.0` to `0.3.0` only when orchestration core is complete.

Step 2: Update README sections:
- single-interface story
- architecture diagram in text
- `ask` command
- old commands as compatibility modes

Step 3: Add concise release notes:
- Hermes as orchestrator
- OpenClaw as executor
- Nemoclaw boundary stub integrated
- central policy + verify loop

Step 4: Final validation commands:
```bash
python3 -m compileall miliciano-poc/bin
./bin/miliciano.js --help
./bin/miliciano.js bootstrap --dry-run
./bin/miliciano.js setup --dry-run
./bin/miliciano.js ask "resume cómo operas"
./bin/miliciano.js think "qué motor usas para razonar"
./bin/miliciano.js exec "responde solo OK"
./bin/miliciano.js mission "divide reasoning vs execution vs policy"
./bin/miliciano.js status
./bin/miliciano.js doctor
```
Expected: all commands succeed and the new orchestration path is visible.

Step 5: Commit:
```bash
git add README.md package.json miliciano-poc/bin/*.py docs/
git commit -m "feat: add Miliciano orchestration core"
```

---

## Acceptance Criteria

Miliciano 0.3.0 is done when:
- users can interact through one primary path: `miliciano ask` or default chat
- Hermes is the explicit planner/orchestrator
- OpenClaw is the explicit execution layer
- policy is evaluated before execution
- execution results are verified after execution
- Nemoclaw appears as a real boundary/external layer, even if still stubbed for some outward flows
- old commands still work as wrappers
- status makes orchestration decisions visible

---

## Suggested Execution Order

1. Task 2
2. Task 3
3. Task 4
4. Task 5
5. Task 6
6. Task 7
7. Task 8
8. Task 9

Plan complete and saved. Ready to execute using subagent-driven-development task-by-task.