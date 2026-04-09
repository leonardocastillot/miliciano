# Miliciano v0.4.0 Usable Enterprise Core Implementation Plan

> For Hermes: use subagent-driven-development to execute this plan task-by-task.

Goal: move Miliciano from a promising orchestration prototype to a genuinely usable, comfortable, and more enterprise-ready technological partner.

Architecture: keep Miliciano as the single user-facing partner while hardening four core layers: output UX, routing/cost control, honest readiness, and permission modes. Reuse the existing Python CLI under `miliciano-poc/bin`, avoid over-engineering, and prefer small dict-based state additions over large class hierarchies.

Tech stack: Python CLI, Node wrapper, Hermes CLI, OpenClaw CLI, Nemoclaw CLI, Ollama, JSON state, markdown docs.

---

## Scope for v0.4.0

This release should deliver these concrete outcomes:
- output modes: `simple`, `operator`, `debug`
- less duplicated/noisy output in `ask`, `exec`, and `mission`
- explicit route/cost posture (`cheap`, `balanced`, `max`)
- honest end-to-end readiness categories in `status`
- real permission modes (`plan`, `ask`, `accept-edits`, `execute`, `restricted-boundary`)
- project instruction file support via `MILICIANO.md`

Out of scope for v0.4.0:
- full Nemoclaw outward workflow engine
- IDE extensions
- GitHub Actions integration
- SDK/public extension API
- full enterprise RBAC

---

## Current codebase facts relevant to this plan

Existing command dispatch:
- `miliciano-poc/bin/miliciano` dispatches all subcommands.

Existing orchestration/runtime:
- `miliciano-poc/bin/miliciano_exec.py` owns `ask`, `exec`, `mission`, shell chat, and orchestration.
- `miliciano-poc/bin/miliciano_runtime.py` owns state, routing, policy, auth/model status helpers, and report helpers.
- `miliciano-poc/bin/miliciano_status.py` renders operational state and doctor output.
- `miliciano-poc/bin/miliciano_controls.py` owns `route`, `model`, `auth`, and provider-related UX.
- `miliciano-poc/bin/miliciano_ui.py` owns banner, panel, response rendering, and help text.

Important current issues discovered in repo inspection:
- `miliciano_exec.py` still emits duplicated plan/verification sections in some flows.
- `status` treats several components as ready based mostly on binary/auth presence, not true end-to-end behavior.
- route/cost behavior is implicit rather than productized as user-understandable modes.
- there is no `mode` command or permission mode state yet.
- there is no `MILICIANO.md` project instruction loading path yet.
- the repo currently has no formal test suite; verification must rely on smoke checks and `python3 -m compileall` unless tests are added in this release.

---

## Task 1: Add v0.4.0 plan file

Objective: ensure the implementation plan itself is present in the repo before code changes.

Files:
- Create: `docs/plans/2026-04-08-miliciano-v0.4.0-usable-enterprise-core.md`
- Modify: none
- Test: none

Step 1: Save this plan file.

Step 2: Verify file exists.
Run:
```bash
python3 - <<'PY'
from pathlib import Path
p = Path('docs/plans/2026-04-08-miliciano-v0.4.0-usable-enterprise-core.md')
print(p.exists(), p)
PY
```
Expected: `True docs/plans/...`

Step 3: Commit.
```bash
git add docs/plans/2026-04-08-miliciano-v0.4.0-usable-enterprise-core.md
git commit -m "docs: add Miliciano v0.4.0 implementation plan"
```

---

## Task 2: Add product mode state (`simple`, `operator`, `debug`)

Objective: create a user-facing output mode system without changing orchestration semantics yet.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_controls.py`
- Modify: `miliciano-poc/bin/miliciano`
- Modify: `miliciano-poc/bin/miliciano_ui.py`

Step 1: Extend default state in `miliciano_runtime.py`.
Add a `preferences` block to `default_miliciano_state()` with:
```python
"preferences": {
    "output_mode": "simple",
    "route_mode": "balanced",
    "permission_mode": "ask",
}
```

Step 2: Normalize the new state.
In `normalize_miliciano_state(state)`, ensure `preferences` exists and default missing keys with `setdefault()`.

Step 3: Add lightweight getters/setters in `miliciano_runtime.py`.
Add:
- `get_output_mode()`
- `set_output_mode(mode)`
- `get_route_mode()`
- `set_route_mode(mode)`
- `get_permission_mode()`
- `set_permission_mode(mode)`

Use plain validation sets:
```python
OUTPUT_MODES = {"simple", "operator", "debug"}
ROUTE_MODES = {"cheap", "balanced", "max"}
PERMISSION_MODES = {"plan", "ask", "accept-edits", "execute", "restricted-boundary"}
```

Step 4: Add command handler in `miliciano_controls.py`.
Implement `cmd_mode(args)` with UX:
- `miliciano mode` -> show current modes
- `miliciano mode output simple|operator|debug`
- `miliciano mode route cheap|balanced|max`
- `miliciano mode permission plan|ask|accept-edits|execute|restricted-boundary`

Use existing `panel(...)` UI style.

Step 5: Wire command dispatch in `miliciano-poc/bin/miliciano`.
Add:
```python
if sub == "mode":
    cmd_mode(args)
    return
```

Step 6: Update help text in `miliciano_ui.py`.
Add `miliciano mode` to `usage()` and explain all three mode families briefly.

Step 7: Verify syntax.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```
Expected: compile succeeds.

Step 8: Verify CLI behavior.
Run:
```bash
./bin/miliciano.js mode
./bin/miliciano.js mode output operator
./bin/miliciano.js mode route cheap
./bin/miliciano.js mode permission plan
./bin/miliciano.js mode
```
Expected:
- current values render cleanly
- state updates persist
- invalid values are rejected with a clear message

Step 9: Commit.
```bash
git add miliciano-poc/bin/miliciano miliciano-poc/bin/miliciano_runtime.py miliciano-poc/bin/miliciano_controls.py miliciano-poc/bin/miliciano_ui.py
git commit -m "feat: add Miliciano output route and permission modes"
```

---

## Task 3: Make response rendering depend on output mode

Objective: reduce noise by shaping output to the selected mode.

Files:
- Modify: `miliciano-poc/bin/miliciano_exec.py`
- Modify: `miliciano-poc/bin/miliciano_ui.py`
- Modify: `miliciano-poc/bin/miliciano_runtime.py`

Step 1: Add an orchestration formatter in `miliciano_exec.py`.
Create helper:
- `format_partner_response(decision, plan_text, exec_out, verification, raw_summary=None)`

Behavior:
- `simple`: show only the final user-facing answer or the shortest useful output
- `operator`: show Plan / Execution / Verification sections
- `debug`: show route, intent, policy, plan, execution, verification

Read mode from `get_output_mode()`.

Step 2: Refactor `render_orchestration_summary(...)`.
Replace the current hardcoded section builder with the new formatter logic.

Step 3: Clean local fast-path behavior.
In `call_local_ollama_query(...)`, return the cleaned model output instead of the current empty string on stream success.
Current code returns:
```python
if rc == 0:
    return rc, "", session_id
```
Change it to return the actual cleaned text.

Step 4: Add minimal structured debug rows.
In debug mode, prepend compact metadata such as:
- `mode`
- `intent`
- `target`
- `route`
- `policy`

Do not expose these in `simple` mode.

Step 5: Make `response_box(...)` resilient to sectioned output.
In `miliciano_ui.py`, preserve blank lines between sections and do not over-wrap already short labels.
Keep the implementation simple.

Step 6: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 7: Smoke test three output modes.
Run:
```bash
./bin/miliciano.js mode output simple
./bin/miliciano.js ask "resume en una línea cómo operas"
./bin/miliciano.js mode output operator
./bin/miliciano.js mission "explica en dos líneas reasoning vs execution"
./bin/miliciano.js mode output debug
./bin/miliciano.js exec "responde solo OK"
```
Expected:
- simple is short
- operator is structured
- debug includes intent/route/policy details

Step 8: Commit.
```bash
git add miliciano-poc/bin/miliciano_exec.py miliciano-poc/bin/miliciano_ui.py miliciano-poc/bin/miliciano_runtime.py
git commit -m "feat: add output-mode aware partner responses"
```

---

## Task 4: Reduce duplicated planning and verification text

Objective: remove repeated sections that make Miliciano feel noisy and unpolished.

Files:
- Modify: `miliciano-poc/bin/miliciano_exec.py`

Step 1: Add a normalization helper.
Implement:
- `normalize_plan_text(plan_text)`
- `normalize_verification_summary(summary)`

The helper should:
- remove exact repeated blocks
- remove repeated headers if the same section appears twice
- keep order stable
- avoid complex parsing; line/block dedup is enough for v0.4.0

Step 2: Apply normalization right after planning.
In `orchestrate_partner_request(...)`, normalize `plan_text` immediately after `call_hermes_query(...)` succeeds.

Step 3: Apply normalization right after verification.
Normalize `verification['summary']` before building the final user-facing output.

Step 4: Add one safety guard.
If normalization empties the text accidentally, fall back to the original text.

Step 5: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 6: Verify with current noisy flows.
Run:
```bash
./bin/miliciano.js mode output operator
./bin/miliciano.js exec "responde solo OK"
./bin/miliciano.js mission "explica en dos líneas reasoning vs execution"
```
Expected:
- no duplicated `OBJETIVO/PLAN/CRITERIO_DE_VERIFICACION` blocks
- verification summary appears once

Step 7: Commit.
```bash
git add miliciano-poc/bin/miliciano_exec.py
git commit -m "fix: dedupe planning and verification output"
```

---

## Task 5: Formalize route modes (`cheap`, `balanced`, `max`)

Objective: make cost posture explicit and configurable.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_controls.py`
- Modify: `miliciano-poc/bin/miliciano_ui.py`

Step 1: Add route-mode-aware selection helper.
Implement in `miliciano_runtime.py`:
- `resolve_route_mode_for_prompt(prompt)`
- `apply_route_mode_override(route, prompt)`

Suggested behavior:
- `cheap`: prefer `fast` for short/simple tasks; avoid premium reasoning unless explicitly forced
- `balanced`: current default behavior
- `max`: prefer `reasoning` for ambiguous/important requests and keep local mostly as fallback/helper

Step 2: Integrate into `resolve_hermes_route_for_prompt(...)`.
Wherever the route is chosen, apply the route mode override before returning the final route.

Step 3: Add route warning in `print_route_overview()`.
If route mode is `cheap` but `fast` is not local/custom, show a warning row.
If route mode is `cheap` and no local model is available, show pending/warn.

Step 4: Update usage/help in `miliciano_ui.py`.
Document the new route posture concept.

Step 5: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 6: Smoke test.
Run:
```bash
./bin/miliciano.js mode route cheap
./bin/miliciano.js ask "resume este texto en una frase"
./bin/miliciano.js mode route max
./bin/miliciano.js ask "analiza esta arquitectura y dime riesgos"
./bin/miliciano.js route
```
Expected:
- cheap visibly favors local/simple path
- max visibly favors deeper reasoning path
- route panel explains posture clearly

Step 7: Commit.
```bash
git add miliciano-poc/bin/miliciano_runtime.py miliciano-poc/bin/miliciano_controls.py miliciano-poc/bin/miliciano_ui.py
git commit -m "feat: add route posture modes for cost-aware routing"
```

---

## Task 6: Add honest end-to-end readiness checks

Objective: make `status` reflect real workflow health instead of just installed components.

Files:
- Modify: `miliciano-poc/bin/miliciano_status.py`
- Modify: `miliciano-poc/bin/miliciano_runtime.py`

Step 1: Add probe helpers in `miliciano_runtime.py`.
Implement small probes:
- `probe_reasoning_path()`
- `probe_execution_path()`
- `probe_local_path()`
- `probe_boundary_path()`

Keep them compact and timeout-bound.
Suggested probes:
- reasoning: a short Hermes prompt with expected short answer
- execution: OpenClaw `Responde solo OK`
- local: short Ollama prompt if local route/model exists
- boundary: check Nemoclaw availability plus explicit pending status if runtime path remains stub

Each should return a dict like:
```python
{"ok": True|False, "summary": "...", "kind": "ready|pending|error|info"}
```

Step 2: Use probes in `render_session_status()`.
Replace the current high-level `reasoning_ok`, `execution_ok`, `policy_ok` assumptions with a richer split:
- installed/binary readiness
- auth readiness
- end-to-end reasoning readiness
- end-to-end execution readiness
- end-to-end local readiness
- end-to-end boundary readiness

Step 3: Add explicit panel.
Create a new panel in `miliciano_status.py`:
- `SALUD END-TO-END`
with rows for reasoning/execution/local/boundary.

Step 4: Keep probe cost bounded.
Do not run full expensive probes when mode is cheap or when binaries are missing. Exit early with `pending`/`error`.

Step 5: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 6: Verify status.
Run:
```bash
./bin/miliciano.js status
```
Expected:
- status includes explicit end-to-end rows
- broken workflows show pending/error even if binaries exist
- boundary is not overstated as fully ready if still partial

Step 7: Commit.
```bash
git add miliciano-poc/bin/miliciano_status.py miliciano-poc/bin/miliciano_runtime.py
git commit -m "feat: add honest end-to-end readiness checks"
```

---

## Task 7: Turn policy verdicts into real permission modes

Objective: make policy behavior product-legible and safer.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_exec.py`
- Modify: `miliciano-poc/bin/miliciano_controls.py`
- Modify: `miliciano-poc/bin/miliciano_ui.py`

Step 1: Extend `build_policy_result(...)`.
Add fields:
- `mode`
- `next_step`
- `allowed_actions`

Keep backward compatibility with existing keys.

Step 2: Make `evaluate_policy_for_prompt(...)` consult permission mode.
Suggested logic:
- `plan`: deny all execution; allow reasoning only
- `ask`: current sensitive/external behavior remains confirm/prompt-oriented
- `accept-edits`: allow reasoning and file-edit-style work, but keep command/network/external actions in ask/blocked state
- `execute`: allow non-destructive execution inside current trust boundary
- `restricted-boundary`: deny any outward/external path unless explicitly forced and approved

For v0.4.0, since there is no interactive approval tool inside Miliciano yet, return clear actionable messages such as:
- `Bloqueado por modo plan...`
- `Requiere aprobación: cambia a mode permission execute o usa boundary explícito...`

Step 3: Apply policy in orchestration.
In `orchestrate_partner_request(...)`, enforce permission-mode-derived verdicts before planning/execution.
Do not continue into OpenClaw if the mode blocks execution.

Step 4: Expose permission mode in trace and status.
- add current permission mode to trace report
- add current permission mode to status or mode panel

Step 5: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 6: Smoke test.
Run:
```bash
./bin/miliciano.js mode permission plan
./bin/miliciano.js exec "responde solo OK"
./bin/miliciano.js mode permission ask
./bin/miliciano.js boundary "quiero exponer un webhook externo"
./bin/miliciano.js mode permission execute
./bin/miliciano.js exec "responde solo OK"
```
Expected:
- plan blocks execution cleanly
- ask warns/requires action for risky workflows
- execute allows normal execution

Step 7: Commit.
```bash
git add miliciano-poc/bin/miliciano_runtime.py miliciano-poc/bin/miliciano_exec.py miliciano-poc/bin/miliciano_controls.py miliciano-poc/bin/miliciano_ui.py
git commit -m "feat: add permission modes to orchestration policy"
```

---

## Task 8: Add `MILICIANO.md` project instruction loading

Objective: give projects a first-class instruction surface similar to a team playbook.

Files:
- Modify: `miliciano-poc/bin/miliciano_runtime.py`
- Modify: `miliciano-poc/bin/miliciano_exec.py`
- Modify: `README.md`
- Create: `MILICIANO.md` (optional example in repo root)

Step 1: Add project instruction locator.
In `miliciano_runtime.py`, implement:
- `find_miliciano_project_file(start_dir=None)`
- `load_miliciano_project_instructions(start_dir=None)`

Behavior:
- search current working directory upward for `MILICIANO.md`
- return file path and compact content
- keep load size bounded (e.g. first 200-300 lines or a character cap)

Step 2: Inject project instructions into prompts.
In `call_hermes_query(...)` and, if useful, in `run_execution_with_openclaw(...)`, prepend a compact block like:
```text
Instrucciones de proyecto activas desde MILICIANO.md:
...
```
Only when the file exists.

Step 3: Expose active project instructions in status or trace.
A small row like:
- `MILICIANO.md  ready  /path/...`
- or `MILICIANO.md  pending  no detectado`

Step 4: Document in README.
Add a section describing `MILICIANO.md` as the project/team instruction file.
Include a short example.

Step 5: Add example file in repo root.
Create `MILICIANO.md` with a minimal example such as:
```md
# MILICIANO.md

- Responde en español para este proyecto.
- Prioriza cambios mínimos y verificables.
- Antes de ejecutar cambios riesgosos, explica impacto.
```

Step 6: Verify compile.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```

Step 7: Smoke test.
Run from repo root:
```bash
./bin/miliciano.js ask "cómo debes comportarte en este proyecto"
./bin/miliciano.js status
```
Expected:
- answer reflects project instructions
- status shows the file was detected

Step 8: Commit.
```bash
git add MILICIANO.md README.md miliciano-poc/bin/miliciano_runtime.py miliciano-poc/bin/miliciano_exec.py
git commit -m "feat: add MILICIANO.md project instruction support"
```

---

## Task 9: Refresh help and README around partner UX

Objective: make product language match the strengthened experience.

Files:
- Modify: `README.md`
- Modify: `miliciano-poc/bin/miliciano_ui.py`

Step 1: Update README intro.
Replace CLI-first wording with partner-first wording.
Mention:
- technological partner
- output modes
- route modes
- permission modes
- `MILICIANO.md`

Step 2: Update help text examples.
Add examples for:
- `miliciano mode`
- `miliciano ask`
- `miliciano route`
- `miliciano boundary`

Step 3: Keep wording concise.
Do not over-explain internal architecture in the default help text.

Step 4: Verify user-visible help.
Run:
```bash
./bin/miliciano.js --help
```
Expected:
- new commands and concepts appear cleanly
- wording feels productized, not purely developer-internal

Step 5: Commit.
```bash
git add README.md miliciano-poc/bin/miliciano_ui.py
git commit -m "docs: refresh Miliciano help and README for v0.4.0"
```

---

## Task 10: Full smoke verification for v0.4.0

Objective: prove the scoped release works together.

Files:
- Modify: none
- Test: CLI smoke commands only unless formal tests are added

Step 1: Compile all Python runtime files.
Run:
```bash
python3 -m compileall miliciano-poc/bin
```
Expected: success.

Step 2: Check help and mode surfaces.
Run:
```bash
./bin/miliciano.js --help
./bin/miliciano.js mode
```
Expected: mode command documented and visible.

Step 3: Check route and status surfaces.
Run:
```bash
./bin/miliciano.js route
./bin/miliciano.js status
./bin/miliciano.js trace
```
Expected: route mode, permission mode, and end-to-end health are visible.

Step 4: Check partner responses across modes.
Run:
```bash
./bin/miliciano.js mode output simple
./bin/miliciano.js ask "resume cómo operas en una línea"
./bin/miliciano.js mode output operator
./bin/miliciano.js mission "explica en dos líneas reasoning vs execution"
./bin/miliciano.js mode output debug
./bin/miliciano.js exec "responde solo OK"
```
Expected:
- no duplicated sections
- mode differences are obvious
- exec still works

Step 5: Check permission enforcement.
Run:
```bash
./bin/miliciano.js mode permission plan
./bin/miliciano.js exec "responde solo OK"
./bin/miliciano.js mode permission execute
./bin/miliciano.js exec "responde solo OK"
```
Expected:
- plan blocks execution
- execute allows it

Step 6: Check project instruction file support.
Run:
```bash
./bin/miliciano.js ask "qué instrucciones de proyecto tienes activas"
```
Expected:
- answer acknowledges `MILICIANO.md` guidance

Step 7: Final commit.
```bash
git add -A
git commit -m "feat: ship Miliciano v0.4.0 usable enterprise core"
```

---

## Good outcome criteria

v0.4.0 is successful when:
- Miliciano feels cleaner and more comfortable by default
- token/cost posture is explicit and user-controllable
- `status` is more honest about real workflow health
- permission modes affect orchestration behavior in visible ways
- projects can shape Miliciano via `MILICIANO.md`
- the product feels more like a technological partner and less like a thin CLI wrapper

---

## Next logical release after v0.4.0

v0.5.0 should target:
- stronger Nemoclaw outward workflows
- GitHub Actions integration
- team memory surfaces
- reusable team skills
- exportable audit traces
- initial IDE/distribution layer
