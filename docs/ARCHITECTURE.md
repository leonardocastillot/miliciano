# Miliciano Architecture

Comprehensive architecture documentation for the Miliciano agent orchestration system.

---

## System Overview

Miliciano implements a three-layer agent architecture:

1. **Hermes (Brain)** - Reasoning and planning layer
2. **Nemoclaw (Firewall)** - Security policy enforcement layer
3. **OpenClaw (Hands)** - Execution and action layer

```
┌──────────────────────────────────────────────────────────┐
│                     User Interface                        │
│                  (CLI / HTTP / API)                      │
└───────────────────────┬──────────────────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         │    miliciano_runtime.py     │
         │   Core Orchestration        │
         └──────────────┬──────────────┘
                        │
      ┌─────────────────┼─────────────────┐
      │                 │                 │
┌─────▼─────┐    ┌──────▼──────┐   ┌────▼──────┐
│  Hermes   │    │  Nemoclaw   │   │ OpenClaw  │
│    🧠     │    │     🛡️      │   │     ✋    │
│ Reasoning │ →  │   Policy    │ → │ Execution │
└───────────┘    └─────────────┘   └───────────┘
      │                 │                 │
      └─────────────────┼─────────────────┘
                        │
                   ┌────▼─────┐
                   │ Obsidian │
                   │  Vault   │
                   │    📚    │
                   └──────────┘
```

---

## Component Architecture

### 1. Hermes (Reasoning Layer)

**Purpose**: High-level reasoning, analysis, and planning.

**Implementation**:
- CLI wrapper: `hermes chat`, `hermes profile`
- Profile: `~/.hermes/profiles/miliciano/`
- Multi-provider support (OpenAI, Anthropic, Groq, etc.)

**Responsibilities**:
- Understand user intent
- Break down complex tasks
- Generate execution plans
- Provide reasoning and justification

**Integration**:
```python
# miliciano_exec.py
def call_hermes_query(prompt):
    route = choose_route_for_prompt(prompt)
    provider, model = resolve_hermes_route(route)
    run(["hermes", "chat", "--provider", provider, "-m", model, "-q", prompt])
```

---

### 2. Nemoclaw (Security Layer)

**Purpose**: Policy enforcement and security controls.

**Implementation**:
- Policy engine: `miliciano_policy.py`
- Fallback: `SimplePolicy` (regex patterns)
- Configuration: `~/.config/miliciano/policy.yaml`

**Responsibilities**:
- Validate actions against security policy
- Block dangerous operations
- Log all operations for audit
- Enforce resource limits

**Policy Flow**:
```python
action = {
    "type": "openclaw_agent",
    "message": "user command"
}

# Check policy
policy_result = policy_engine.check_action(action)

if not policy_result["allowed"]:
    raise PolicyViolation(reason)

# Continue with execution
```

**Enforcement Modes**:
- `enforce`: Block dangerous operations (production)
- `audit`: Log violations but allow (testing)
- `disabled`: No checks (not recommended)

---

### 3. OpenClaw (Execution Layer)

**Purpose**: Execute tasks, interact with systems.

**Implementation**:
- CLI: `openclaw agent`
- Gateway: HTTP server for agent communication
- Configuration: `~/.openclaw/`

**Responsibilities**:
- Execute approved actions
- Handle tool invocations
- Manage API authentication
- Return execution results

**Integration**:
```python
# miliciano_runtime.py
def run_openclaw_agent(message):
    # 1. Policy check
    policy.check_action(action)
    
    # 2. Execute
    result = run(["openclaw", "agent", "--agent", "main", "--message", message])
    
    # 3. Audit log
    policy.audit_log(action, policy_result, execution_result)
```

---

## Data Flow

### Standard Execution Flow

```
1. User Input
   ↓
2. Input Validation (miliciano_validators.py)
   ↓
3. Route Selection (reasoning/execution/fast/local/fallback)
   ↓
4. Hermes Reasoning (optional)
   ├─ Analyzes intent
   ├─ Generates plan
   └─ Creates execution instructions
   ↓
5. Policy Check (miliciano_policy.py)
   ├─ Validates action
   ├─ Checks against blocked patterns
   └─ Logs to audit trail
   ↓
6. Execution (run_openclaw_agent)
   ├─ Calls OpenClaw agent
   ├─ Monitors execution
   └─ Captures output
   ↓
7. Result Logging
   ├─ Structured logs (miliciano_logging.py)
   ├─ Audit trail (~/.config/miliciano/audit.log)
   └─ Obsidian memory (~/Obsidian Vault/)
   ↓
8. User Response
```

### Mission Flow (Plan + Execute)

```
1. User: "miliciano mission 'automate testing'"
   ↓
2. Phase 1: Hermes Planning
   ├─ Analyzes objective
   ├─ Breaks into steps
   └─ Generates detailed plan
   ↓
3. Phase 2: Policy Validation
   └─ Checks each step against policy
   ↓
4. Phase 3: OpenClaw Execution
   ├─ Executes plan steps
   ├─ Monitors progress
   └─ Handles errors
   ↓
5. Results + Memory
   └─ Saved to Obsidian with full context
```

---

## Routing System

Miliciano uses dynamic routing to select the appropriate model based on task characteristics.

### Routes

| Route | Purpose | Default Model | When Used |
|-------|---------|---------------|-----------|
| **reasoning** | Complex analysis, planning | OpenAI GPT-4 | Long prompts, complex questions, "how", "why" |
| **execution** | Primary task execution | OpenAI GPT-4 | Default for `exec` and `mission` |
| **fast** | Quick responses | Ollama Qwen2.5:3b | Short prompts, simple queries |
| **local** | Offline inference | Ollama (user choice) | Explicit local mode, no internet |
| **fallback** | Backup when primary fails | OpenAI GPT-3.5 | Primary provider down or quota exceeded |

### Route Selection Logic

```python
def choose_route_for_prompt(prompt):
    # Check length
    if len(prompt) < 280:
        if contains_fast_keywords(prompt):
            return "fast"
    
    # Check keywords
    if contains_reasoning_keywords(prompt):
        return "reasoning"
    
    # Default
    return "execution"
```

**Reasoning Keywords**: `analyze`, `explain`, `design`, `architect`, `plan`, `strategy`  
**Fast Keywords**: `list`, `show`, `status`, `simple`, `quick`

---

## State Management

### Configuration Files

```
~/.config/miliciano/
├── config.json           # Main state
├── policy.yaml           # Security policy
├── audit.log             # Audit trail
└── logs/
    └── miliciano.log     # Structured logs

~/.hermes/profiles/miliciano/
├── config.yaml           # Hermes configuration
├── auth.json             # Hermes credentials
└── SOUL.md               # Profile identity

~/.openclaw/
├── openclaw.json         # OpenClaw defaults
└── agents/main/agent/
    └── auth-profiles.json # OpenClaw credentials

~/.nemoclaw/
└── credentials.json      # Nemoclaw credentials
```

### State Structure

```json
{
  "hermes": {
    "provider": "openai-codex",
    "model": "gpt-4"
  },
  "openclaw": {
    "model": "openai-codex/gpt-4"
  },
  "nemoclaw": {
    "model": null
  },
  "routing": {
    "reasoning": "openai-codex/gpt-4",
    "execution": "openai-codex/gpt-4",
    "fast": "custom/qwen2.5:3b",
    "local": "custom/qwen2.5:3b",
    "fallback": "openai-codex/gpt-3.5-turbo"
  },
  "ollama": {
    "preferred_model": "qwen2.5:3b",
    "auto_install": true
  }
}
```

---

## Security Architecture

### Defense in Depth

```
Layer 1: Input Validation
├─ Sanitize prompts
├─ Validate provider/model names
├─ Block shell metacharacters
└─ Prevent path traversal

Layer 2: Policy Enforcement
├─ Pattern-based blocking (SimplePolicy)
├─ Nemoclaw full policy (when available)
├─ Resource limits
└─ Audit logging

Layer 3: Execution Sandboxing
├─ Limited permissions
├─ Docker isolation (future)
└─ Network restrictions (future)

Layer 4: Credential Protection
├─ Encrypted storage (optional)
├─ OS keyring integration
└─ Minimal scope tokens
```

### Threat Model

**Protected Against**:
- ✅ Shell injection
- ✅ Path traversal
- ✅ Command injection
- ✅ Code evaluation (`eval`)
- ✅ Data destruction (`rm -rf`)
- ✅ Privilege escalation (`sudo`)

**Not Protected Against** (future work):
- ⏸️ Resource exhaustion (CPU/memory bombs)
- ⏸️ Network-based attacks (if allowed through policy)
- ⏸️ Time-of-check/time-of-use races

---

## Observability

### Logging Architecture

```
┌─────────────────────────────────────┐
│     Application Code                │
│  (miliciano_runtime.py, etc.)       │
└──────────────┬──────────────────────┘
               │
               ├─ log_operation()
               ├─ log_error()
               └─ log_security_event()
               │
        ┌──────▼──────────────┐
        │ StructuredLogger    │
        │ (miliciano_logging) │
        └──────┬──────────────┘
               │
        ┌──────┴──────┐
        │             │
   ┌────▼────┐   ┌───▼──────┐
   │ Console │   │   File   │
   │ (human) │   │  (JSON)  │
   └─────────┘   └──────────┘
```

**Log Levels**:
- `DEBUG`: Detailed diagnostic info
- `INFO`: General operations
- `WARNING`: Non-critical issues
- `ERROR`: Errors that need attention
- `CRITICAL`: System-level failures

### Health Monitoring

```
┌───────────────────────────────┐
│   Health Check Endpoint       │
│   GET /health                 │
└──────────┬────────────────────┘
           │
    ┌──────▼──────────┐
    │ health_check    │
    │ _json()         │
    └──────┬──────────┘
           │
    ┌──────┴────────┐
    │ Check:        │
    ├─ Hermes       │
    ├─ OpenClaw     │
    ├─ Nemoclaw     │
    └─ Ollama       │
           │
    ┌──────▼──────────┐
    │ {              │
    │   "healthy": T/F│
    │   "components"  │
    │ }              │
    └─────────────────┘
```

---

## Extension Points

### Adding New Providers

```python
# 1. Add to VALID_PROVIDERS in miliciano_validators.py
VALID_PROVIDERS = ["openai", "anthropic", "custom_provider"]

# 2. Configure in routing
miliciano route set reasoning custom_provider/model-name

# 3. Add auth
miliciano auth add hermes custom_provider api-key
```

### Adding Policy Rules

```yaml
# ~/.config/miliciano/policy.yaml
blocked_commands:
  - pattern: "\\bcustom_dangerous_command\\b"
    description: "My dangerous command"
    risk: high
```

### Custom Logging

```python
from miliciano_logging import get_logger

logger = get_logger()
logger.info("Custom operation", 
           custom_field="value",
           metric=123)
```

---

## Performance Considerations

### Latency Sources

1. **Network I/O**: Remote LLM API calls (1-5s)
2. **Policy Check**: Pattern matching (< 10ms)
3. **Logging**: File I/O (< 5ms)
4. **Subprocess**: Shell command overhead (50-100ms)

### Optimization Strategies

- **Caching**: State cached in-memory
- **Parallel**: Policy check + execution preparation
- **Local Fallback**: Fast route uses local Ollama
- **Async**: Background audit logging

---

## Deployment Patterns

### Single User (Development)
```
[User] → [Miliciano CLI] → [Local Services]
```

### Team (Shared Gateway)
```
[Users] → [Shared Hermes/OpenClaw] → [Shared Policy]
```

### Enterprise (Distributed)
```
[Users] → [Load Balancer] → [Miliciano Instances]
                           → [Shared Config]
                           → [Centralized Logs]
```

---

## Future Architecture

### Planned Improvements

1. **Microservices**: Split components into services
2. **gRPC**: Replace subprocess with gRPC
3. **Queue**: Async job queue for long tasks
4. **Cache**: Redis for state/config
5. **Metrics**: Prometheus export
6. **Tracing**: OpenTelemetry integration

---

**Version**: 0.3.0  
**Last Updated**: 2026-04-10
