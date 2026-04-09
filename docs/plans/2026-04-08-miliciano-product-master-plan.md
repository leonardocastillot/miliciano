# Miliciano Product Master Plan

> For Hermes: use subagent-driven-development to execute this plan track-by-track.

Goal: turn Miliciano into a genuinely usable, comfortable, enterprise-grade AI technological partner that developers, founders, and teams can trust for daily work.

Architecture: keep Miliciano as the only visible product surface. Hermes remains the reasoning/orchestration brain, OpenClaw remains execution, Ollama/local runtimes remain the cheap reflex path, and Nemoclaw becomes the enterprise boundary, policy, and outward-control layer. The product should feel like one partner, not a bundle of tools.

Tech stack: Python CLI runtime, Node wrapper, Hermes CLI, OpenClaw CLI, Nemoclaw CLI, Ollama, JSON state, docs, future IDE/gateway/CI integrations.

---

## Product thesis

Miliciano is not a chatbot, not a coding copilot, and not just an agent runner.

Miliciano is an AI technological partner.

That means the product must:
- understand the user and project context
- reason when needed
- execute when useful
- protect the system when risk appears
- remember operational knowledge
- stay comfortable to use every day
- expose enterprise-grade traceability and controls

The winning experience is not feature parity with a competitor. The winning experience is: "I have a technological partner that helps me operate faster, safer, and with less mental load."

---

## Current repo reality

What already exists:
- unified CLI entrypoint via `miliciano`
- `ask`, `boundary`, `trace`, `status`, `setup`, `bootstrap`, `doctor`
- orchestration concept with Hermes/OpenClaw/Nemoclaw/Ollama
- basic routing: reasoning, execution, fast, local, fallback
- basic policy and trace reporting
- bootstrap/setup flow and runtime checks
- local model support with Ollama

Main gaps:
- product language is still CLI-centric instead of partner-centric
- permission and approval modes are still primitive
- enterprise boundary is mostly conceptual, not fully operational
- status/readiness can still overstate real end-to-end health
- there is no formal product UX layer for daily comfort and confidence
- no explicit team/enterprise controls pack yet
- no strong IDE/CI/team distribution layer yet
- no formal test/eval harness for product trust

---

## Product north star

Miliciano should become:
- the default technological partner for an individual builder
- the shared operational AI partner for a technical team
- the auditable AI operating layer for an enterprise

North-star product statement:
"Miliciano helps people and teams think, execute, and operate across their technology stack with memory, control, and trust."

North-star experience:
- one interface
- one identity
- multiple internal engines
- low-friction setup
- safe execution
- visible trace
- cost-aware behavior
- excellent defaults

---

## Non-negotiable product principles

### 1) One visible interface
The user talks to Miliciano. Internal organs are not the product.

### 2) Comfort first
If the experience is annoying, brittle, noisy, or hard to understand, it fails even if the architecture is clever.

### 3) Cost intelligence
Miliciano must know when to use local, when to use premium reasoning, and when not to invoke expensive paths.

### 4) Trust over theatrics
Never fake readiness. Never hide uncertainty. Never silently take risky actions.

### 5) Enterprise by design
Audit trail, permissions, secrets hygiene, and outbound control must be designed in early, not bolted on later.

### 6) Open and modular
Provider-agnostic, self-hostable where possible, and extensible through skills, hooks, MCP, plugins, and policy packs.

### 7) Partner behavior
Miliciano must feel proactive, contextual, and reliable, not like a stateless assistant.

---

## Strategic product pillars

## Pillar A: Daily usability and comfort
Miliciano must feel easy, fluid, and pleasant.

Deliverables:
- cleaner outputs with less noise and duplication
- obvious command entrypoints and better help text
- better interactive shell UX
- stable session continuity and memory continuity
- friendlier progress and explanation layer
- clear error messages with guided recovery

Good outcome:
A non-expert can install Miliciano, ask something useful, and trust what happens next.

## Pillar B: Real partner intelligence
Miliciano must do more than answer.

Deliverables:
- stronger project memory
- better task continuity
- explicit working modes: cheap, balanced, max, debug
- proactive follow-up suggestions
- better intent classification and orchestration
- lightweight planning by default, deeper planning only when warranted

Good outcome:
Miliciano feels like a reliable operating partner, not a prompt box.

## Pillar C: Execution you can trust
Execution must be useful, controllable, and reviewable.

Deliverables:
- stronger execution verification
- one-pass retry only when justified
- clean trace for plan, execution, verification, and errors
- safer defaults for shell/file/git actions
- improved readiness checks that validate real workflows end-to-end

Good outcome:
The user trusts Miliciano with real work because it behaves predictably.

## Pillar D: Enterprise controls and boundary
Nemoclaw must become real product value.

Deliverables:
- permission modes
- approval workflows for sensitive actions
- outbound/webhook/service exposure controls
- secret-aware execution guardrails
- audit logs and policy traces
- boundary verdicts that are understandable to operators

Good outcome:
An enterprise buyer sees policy and control as a strength, not a gap.

## Pillar E: Distribution and ecosystem
Miliciano must live where work happens.

Deliverables:
- terminal remains first-class
- Discord/voice-first operator mode
- GitHub Actions integration
- IDE integrations after core UX is solid
- reusable team skills and instructions
- future lightweight web/admin surface only after core workflow is strong

Good outcome:
Miliciano becomes part of real workflows, not a side experiment.

---

## Product roadmap

## Phase 1: Usable core partner
Target: make Miliciano undeniably usable every day.

### Workstream 1.1: Partner identity in-product
Objective: align the UX around "technological partner".

Tasks:
- update README and help text to describe Miliciano as a technological partner, not just a CLI
- standardize user-facing copy across `ask`, `status`, `trace`, `doctor`, `setup`
- reduce internal component leakage in normal mode
- keep component details available in debug/operator surfaces

Success criteria:
- the product language is coherent
- the default UX feels like one partner

### Workstream 1.2: Comfort and clarity
Objective: remove friction from daily use.

Tasks:
- add output modes: `simple`, `operator`, `debug`
- reduce repeated sections in planning/verification output
- ensure errors always include next-action guidance
- make interactive shell support session names, clear resume cues, and user mode switching

Success criteria:
- default responses are concise and readable
- advanced users can opt into deeper trace without punishing normal users

### Workstream 1.3: Cost-aware routing
Objective: prevent token waste.

Tasks:
- formalize routing modes: local-first, balanced, premium
- tune `fast` to stay local whenever the task is simple enough
- only escalate to premium reasoning when complexity merits it
- expose route decisions and cost intent in trace
- add a warning if the configured fast path is not actually cheap/local

Success criteria:
- simple tasks stay cheap
- expensive models are used intentionally, not accidentally

### Workstream 1.4: Honest health/readiness
Objective: make readiness real.

Tasks:
- split readiness into binary/auth/end-to-end categories
- add explicit end-to-end probes for reasoning, execution, local path, and boundary
- show auth coherence clearly for Codex/provider sessions
- downgrade status when a real workflow is broken even if binaries exist

Success criteria:
- `status` reflects reality, not hopeful assumptions

---

## Phase 2: Trustworthy execution and policy
Target: make Miliciano safe enough for serious work.

### Workstream 2.1: Permission modes
Objective: add operator trust controls.

Required modes:
- `plan` = analysis only, no execution
- `ask` = confirm risky actions
- `accept-edits` = allow file edits, confirm command/network/external actions
- `execute` = broader autonomy inside current trust boundary
- `restricted-boundary` = block outward exposure unless explicitly approved

Success criteria:
- users understand what Miliciano can do in each mode
- enterprises can map modes to policy requirements

### Workstream 2.2: Strong verification and rollback thinking
Objective: execution must be reviewable and controlled.

Tasks:
- strengthen post-execution verification prompts
- label unresolved executions as incomplete, not passed
- keep diff/command summaries for review
- prepare rollback or remediation hints when something fails

Success criteria:
- execution results become trustworthy and auditable

### Workstream 2.3: Boundary productization with Nemoclaw
Objective: turn Nemoclaw into a visible enterprise advantage.

Tasks:
- implement real outward workflows for webhooks, service exposure, and external agents
- require policy review before any public exposure path
- show boundary decisions in trace/status
- define what Nemoclaw owns versus what Hermes/OpenClaw own

Success criteria:
- Nemoclaw is no longer a stub; it becomes part of the product promise

---

## Phase 3: Team and enterprise productization
Target: make Miliciano credible beyond solo use.

### Workstream 3.1: Team memory and instructions
Objective: make Miliciano useful across teams and repos.

Tasks:
- introduce `MILICIANO.md` as team/project instruction file
- support team-specific skills and reusable workflows
- expose memory scopes: personal, project, team
- add explicit visibility into what memory/instructions are active

Success criteria:
- a team can shape Miliciano to its standards without retraining from scratch every session

### Workstream 3.2: Audit and compliance surface
Objective: make enterprise controls tangible.

Tasks:
- event logs for reasoning/execution/boundary decisions
- exportable trace for sensitive sessions
- secret redaction verification
- approval records for risky actions

Success criteria:
- an enterprise operator can review what happened and why

### Workstream 3.3: Distribution for real work
Objective: meet users where they operate.

Priority order:
1. terminal polish
2. Discord operator/voice mode
3. GitHub Actions integration
4. IDE support
5. lightweight web/admin surface

Success criteria:
- users do not need to leave their normal environment to get value

---

## Phase 4: Platform and market leadership
Target: become category-defining, not just usable.

### Workstream 4.1: Agent SDK / extension surface
Objective: let others build on Miliciano.

Tasks:
- formalize plugin/skill/hook contracts
- publish reusable integration patterns
- support custom policy packs and custom agents
- expose a stable orchestration API surface

### Workstream 4.2: Evaluation and proof
Objective: make quality measurable.

Tasks:
- create benchmark tasks for setup, routing, execution, review, and boundary
- measure cost per task, success rate, correction rate, time-to-result
- compare local-first versus premium modes
- create internal "trust score" and "comfort score" product metrics

### Workstream 4.3: Category messaging
Objective: own the market language.

Tasks:
- ship a product manifesto
- define core ICPs and website messaging
- develop narratives for developers, founders, and enterprises
- present Miliciano as the AI technological partner, not a generic assistant

---

## Product surface that should exist in a strong v1

### Essential commands
- `miliciano ask`
- `miliciano status`
- `miliciano trace`
- `miliciano setup`
- `miliciano doctor`
- `miliciano mode`
- `miliciano auth`
- `miliciano route`
- `miliciano boundary`

### Essential user concepts
- partner identity
- permission mode
- route mode
- trace/audit
- memory scope
- boundary policy

### Essential enterprise concepts
- approvals
- auditability
- provider control
- outbound control
- local-first deployment option
- policy-driven execution

---

## What “great” looks like

Miliciano is in strong shape when:
- a new user can install it and get value fast
- a power user can trust it with meaningful technical work
- a team can encode standards into it
- an enterprise can understand and govern it
- local/cheap routing is not a second-class citizen
- the system feels coherent and comfortable
- users describe it as a partner, not a tool wrapper

---

## Immediate implementation priorities

Priority 1:
- output modes (`simple`, `operator`, `debug`)
- reduce noisy/repeated output
- honest end-to-end readiness checks
- codex/provider auth coherence checks everywhere relevant

Priority 2:
- permission modes
- stronger boundary workflows with Nemoclaw
- local-first cost routing
- `MILICIANO.md` support

Priority 3:
- GitHub Actions integration
- Discord operator mode improvements
- audit/event export
- reusable team workflows/skills

Priority 4:
- IDE integrations
- SDK surface
- enterprise admin controls
- formal evaluation harness

---

## Go / no-go product rule

Do not call Miliciano a complete enterprise product until these are true:
- end-to-end execution health is honest and stable
- permission modes are real
- boundary workflows are real
- local-first cost control is real
- trace and audit are exportable
- team instructions/memory are real

Until then, present Miliciano as an ambitious but fast-moving technological partner platform.

---

## Suggested next implementation plan

Next concrete build plan should target `v0.4.0` with this scope:
- output modes
- real permission modes
- stronger end-to-end health checks
- route/cost policy hardening
- `MILICIANO.md` project instructions
- boundary workflow MVP

That release would move Miliciano from promising prototype toward serious product.
