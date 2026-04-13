# Miliciano

> Agente de IA táctico con razonamiento (Hermes), ejecución (OpenClaw) y política de seguridad (Nemoclaw)

**Por Milytics** | Versión 0.3.0

[![Security](https://img.shields.io/badge/security-hardened-green.svg)](docs/SECURITY.md)
[![Tests](https://img.shields.io/badge/tests-280%2B-blue.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-75%25-brightgreen.svg)](PHASE3_COMPLETE.md)
[![Production Ready](https://img.shields.io/badge/production-7.5%2F10-yellow.svg)](PHASE4_COMPLETE.md)

---

## 🎯 Qué es Miliciano

Miliciano es un CLI que orquesta tres componentes para crear un agente de IA completo:

- **🧠 Hermes** - Cerebro de razonamiento (LLM remoto para análisis y planificación)
- **✋ OpenClaw** - Manos de ejecución (runtime de agentes para ejecutar tareas)
- **🛡️ Nemoclaw** - Firewall de seguridad (capa de política que bloquea operaciones peligrosas)

**Flujo**:
```
Usuario → Hermes (planifica) → Nemoclaw (valida) → OpenClaw (ejecuta) → Resultado
```

---

## ✨ Características

### Seguridad Reforzada (Phase 1-2)
- ✅ **Validación de entrada**: Bloquea inyección de shell, path traversal, SQL injection
- ✅ **Descarga segura**: Verificación de checksums para scripts externos
- ✅ **Política de seguridad**: Patrones bloqueados (`rm -rf`, `eval()`, `| bash`)
- ✅ **Cifrado de credenciales**: API keys cifradas en reposo (opcional)
- ✅ **Registro de auditoría**: Log de todas las operaciones

### Observabilidad (Phase 3-4)
- ✅ **280+ tests**: Suite completa con pytest
- ✅ **Logging estructurado**: JSON logs con rotación automática
- ✅ **Health checks**: Endpoint HTTP `/health` para monitoreo
- ✅ **Métricas**: Duración, éxito/fallo, eventos de seguridad

### Inteligencia
- ✅ **Routing dinámico**: 5 rutas (reasoning, execution, fast, local, fallback)
- ✅ **Multi-proveedor**: OpenAI, Anthropic, Groq, Ollama local, NVIDIA
- ✅ **Grafo de conocimiento**: Integración con Obsidian
- ✅ **Memoria persistente**: Historial de decisiones y skills

### Operación diaria
- ✅ **Shell táctico por modos**: reasoning, plan y unrestricted desde el chat interactivo
- ✅ **Setup y repair**: bootstrap, convergencia local y reparación de wrappers/PATH
- ✅ **Gestión de providers**: auth, provider, model y route desde un solo CLI
- ✅ **Registry de herramientas**: inspección de tools y health operativo

---

## 🚀 Instalación Rápida

### Requisitos
- **OS**: Linux (Ubuntu 22.04+)
- **Runtime**: Node.js >= 18, Python 3.10+
- **Opcional**: Docker (para Nemoclaw full)

### Instalar
```bash
# Instalar Miliciano globalmente
npm install -g @milytics/miliciano

# Setup automático recomendado
miliciano setup --auto

# Alias operativo equivalente
miliciano bootstrap

# Verificar instalación
miliciano status
```

### Configurar API Key
```bash
# Opción 1: Variable de entorno
export OPENAI_API_KEY=sk-...

# Opción 2: Configurar con Miliciano
miliciano auth add openclaw openai-codex sk-...

# Verificar
miliciano status
```

---

## 📖 Uso Básico

### Comandos Principales

#### 1. `think` - Razonamiento
```bash
# Hacer una pregunta, obtener análisis
miliciano think "¿Cómo debería arquitecturar un backend de microservicios?"
```

#### 2. `exec` - Ejecución
```bash
# Ejecutar una tarea
miliciano exec "Listar archivos en /tmp y resumir"
```

#### 3. `mission` - Misión completa
```bash
# Plan (Hermes) + Ejecución (OpenClaw)
miliciano mission "Automatizar el pipeline de testing"
```

#### 4. `shell` - Modo interactivo
```bash
# Chat interactivo táctico
miliciano shell
```

Si el shell interactivo detecta una dependencia faltante, usa:

```bash
miliciano setup
```

`setup` ahora repara automáticamente la dependencia del shell (`prompt_toolkit`) sin depender de que estés parado en la carpeta del repo.
En Debian/Ubuntu también diagnostica si faltan `pip`/`venv` del sistema y propone repararlos antes de instalar el runtime Python local.

Atajos del shell:
- `Shift+Tab` / `Ctrl+T` / `Alt+M` cambia modo
- `Enter` envía
- `Esc+Enter` agrega una nueva línea

### Comandos de Configuración

```bash
# Ver estado de componentes
miliciano status

# Configurar modelo
miliciano model hermes openai-codex/gpt-4
miliciano model openclaw openai-codex/gpt-4

# Configurar routing
miliciano route set reasoning openai-codex/gpt-4
miliciano route set fast custom/qwen2.5:3b
miliciano route sync

# Gestionar auth / providers
miliciano auth add hermes openai sk-...
miliciano provider connect nvidia nvapi-...
miliciano provider activate execution openai-codex/gpt-4

# Permisos y herramientas
miliciano permission enforce
miliciano tools list
miliciano tools health

# Diagnosticar problemas
miliciano doctor
miliciano repair
```

---

## 🔒 Seguridad

### Política de Seguridad

Miliciano bloquea automáticamente operaciones peligrosas:

```bash
# Esto será bloqueado
miliciano exec "rm -rf /"
# ❌ Bloqueado por política de seguridad: Dangerous pattern detected

# Esto está permitido
miliciano exec "ls -la /tmp"
# ✓ Ejecutado correctamente
```

### Modos de Política

```bash
# Enforce (default): Bloquear operaciones peligrosas
export NEMOCLAW_POLICY_MODE=enforce

# Audit: Registrar pero permitir (para testing)
export NEMOCLAW_POLICY_MODE=audit

# Disabled: Sin checks (no recomendado)
export NEMOCLAW_POLICY_MODE=disabled
```

### Configurar Política

Editar `~/.config/miliciano/policy.yaml`:

```yaml
mode: enforce

blocked_commands:
  - pattern: "\\brm\\s+-rf\\b"
    description: "Recursive deletion"
    risk: critical

allowed_commands:
  - pattern: "^(ls|cat|grep)\\b"
    description: "Read-only operations"
    risk: low
```

Ver [docs/SECURITY.md](docs/SECURITY.md) para más detalles.

---

## 📊 Monitoreo

### Logs

```bash
# Logs estructurados en JSON
tail -f ~/.config/miliciano/logs/miliciano.log | jq .

# Filtrar errores
tail -f ~/.config/miliciano/logs/miliciano.log | jq 'select(.level=="ERROR")'

# Eventos de seguridad
tail -f ~/.config/miliciano/logs/miliciano.log | jq 'select(.event_type=="security")'
```

### Health Check

```bash
# HTTP endpoint (requiere Obsidian graph server corriendo)
curl -s http://127.0.0.1:8765/health | jq .
```

### Audit Trail

```bash
# Ver últimas operaciones
cat ~/.config/miliciano/audit.log | tail -10 | jq .
```

---

## ⚙️ Configuración Avanzada

### Variables de Entorno

Ver [.env.example](.env.example) para todas las opciones disponibles.

```bash
# Copiar template
cp .env.example .env

# Editar valores
nano .env

# Cargar en shell
export $(cat .env | grep -v '^#' | xargs)
```

---

## 🗂️ Arquitectura

```
┌─────────────────────────────────────────┐
│         Usuario (CLI)                   │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌───▼────┐  ┌─▼──────┐
│Hermes │  │OpenClaw│  │Nemoclaw│
│ 🧠    │  │  ✋    │  │  🛡️    │
│Razón  │  │Ejecución│ │Política│
└───┬───┘  └───┬────┘  └─┬──────┘
    │          │          │
    └──────────┼──────────┘
               │
          ┌────▼─────┐
          │ Obsidian │
          │  Vault   │
          │   📚     │
          └──────────┘
```

Ver [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para detalles completos.

---

## 🧪 Testing

```bash
# Dependencias de desarrollo
python3 -m pip install -r requirements-dev.txt

# Ejecutar suite principal
npm test

# Ejecutar pytest directo
python3 -m pytest tests/ -v
```

Si tu entorno todavía no tiene `pytest`, mira [TESTING_SETUP.md](TESTING_SETUP.md).

---

## 📚 Documentación

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Arquitectura del sistema
- **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Empaquetado, Docker y despliegue
- **[SECURITY.md](docs/SECURITY.md)** - Modelo de seguridad
- **[TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Solución de problemas
- **[CHANGELOG.md](CHANGELOG.md)** - Historial de cambios
- **[TESTING_SETUP.md](TESTING_SETUP.md)** - Setup de pruebas y cobertura

---

## 🛠️ Desarrollo

### Estructura del Proyecto

```
miliciano/
├── bin/miliciano.js              # Entry point
├── miliciano-poc/bin/            # Scripts Python
├── tests/                        # Suite de tests
├── docs/                         # Documentación
└── package.json                  # npm config
```

---

## 🐛 Solución de Problemas

Ver [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) para soluciones detalladas.

Problemas comunes:
- `miliciano shell` falla por dependencia faltante -> corre `miliciano setup`
- wrapper npm no encuentra Python -> corre `miliciano repair`
- rutas o provider no coinciden -> revisa `miliciano status` y `miliciano route sync`
- tooling local roto -> inspecciona `miliciano tools health`

---

## 🔐 Seguridad

Miliciano endurece entrada, ejecución y auditoría alrededor de Hermes/OpenClaw/Nemoclaw.

Referencias rápidas:
- [docs/SECURITY.md](docs/SECURITY.md)
- [SECURITY_FIXES.md](SECURITY_FIXES.md)
- `miliciano permission <enforce|audit|disabled>`

---

## 📜 Licencia

MIT © Milytics

