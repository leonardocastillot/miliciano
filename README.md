# @milytics/miliciano

Miliciano CLI by Milytics.

Instalación rápida del CLI:

```bash
npm install -g @milytics/miliciano
```

Comandos principales:

```bash
miliciano
miliciano status
miliciano setup
miliciano setup --auto
miliciano setup --dry-run
miliciano bootstrap
miliciano bootstrap --dry-run
miliciano doctor
miliciano repair
miliciano think "..."
miliciano exec "..."
miliciano mission "..."
```

Requisitos base:
- Linux
- python3
- Node.js >= 18
- npm
- curl

Qué hace cada comando:
- `miliciano` abre la consola interactiva.
- `miliciano status` muestra el estado real del stack.
- `miliciano setup` revisa el stack y corrige lo que puede.
- `miliciano setup --auto` intenta dejar el stack listo sin pedir confirmaciones.
- `miliciano setup --dry-run` muestra qué revisaría y qué intentaría corregir, sin tocar el sistema.
- `miliciano bootstrap` hace instalación integral: valida prerequisitos, instala componentes faltantes y termina ejecutando `setup --auto`.
- `miliciano bootstrap --dry-run` te da el plan completo de instalación antes de ejecutar nada.
- `miliciano doctor` corre diagnóstico profundo.
- `miliciano repair` repara wrappers, PATH y sincronización local.

Flujo recomendado desde cero:

1. Instala el CLI:

```bash
npm install -g @milytics/miliciano
```

2. Mira el plan antes de tocar nada:

```bash
miliciano bootstrap --dry-run
```

3. Ejecuta bootstrap:

```bash
miliciano bootstrap
```

4. Si quieres reintentar solo la convergencia/configuración:

```bash
miliciano setup --auto
```

Qué intenta resolver `bootstrap`

- valida prerequisitos esenciales: `python3`, `node`, `npm`, `curl`
- intenta instalar `Hermes` si le das un hook de instalación
- instala `OpenClaw` por defecto con `npm install -g openclaw`
- instala `Nemoclaw` por defecto con `npm install -g nemoclaw`
- instala `Ollama` en modo user-space dentro de `~/.local` usando el release oficial de Linux
- imprime follow-ups útiles antes de la convergencia final
- guarda un reporte en `~/.config/miliciano/install-report.json`
- luego ejecuta `miliciano setup --auto`

Automatización por hooks

Puedes controlar la instalación con variables de entorno. Cada componente acepta:
- `*_INSTALL_CMD`
- `*_INSTALL_URL`

Variables soportadas:

```bash
MILICIANO_HERMES_INSTALL_CMD
MILICIANO_HERMES_INSTALL_URL
MILICIANO_OPENCLAW_INSTALL_CMD
MILICIANO_OPENCLAW_INSTALL_URL
MILICIANO_NEMOCLAW_INSTALL_CMD
MILICIANO_NEMOCLAW_INSTALL_URL
MILICIANO_OLLAMA_INSTALL_CMD
MILICIANO_OLLAMA_INSTALL_URL
```

Ejemplos:

```bash
export MILICIANO_HERMES_INSTALL_CMD='comando-que-instala-hermes'
export MILICIANO_OPENCLAW_INSTALL_CMD='npm install -g openclaw'
export MILICIANO_NEMOCLAW_INSTALL_CMD='npm install -g nemoclaw'
miliciano bootstrap
```

Auth automática de OpenClaw

Si `OPENAI_API_KEY` está presente en la sesión, `miliciano setup --auto` intenta reutilizarla para resolver la auth básica de OpenClaw.

Base local con Ollama

- Si Ollama ya está instalado pero su API no responde, `setup --auto` intenta levantar `ollama serve`.
- Si la API responde pero no hay modelos descargados, Miliciano intenta bajar un modelo base recomendado según el hardware detectado.
- En equipos modestos suele priorizar `qwen2.5:3b` como base local.

Notas operativas

- El runtime principal sigue siendo el CLI Python incluido en `miliciano-poc/bin`.
- `bootstrap` y `setup --auto` priorizan instalación sin `sudo` cuando pueden.
- Para el instalador user-space de Ollama conviene tener `tar` y `zstd` disponibles.
- `doctor` omite OpenClaw si el binario no existe, en vez de romper el flujo completo.
- Miliciano enlaza `~/.hermes/.env` hacia `~/.hermes/profiles/miliciano/.env` cuando detecta que falta el `.env` del perfil.
- `install-report.json` deja trazabilidad del último bootstrap/setup para revisar qué intentó hacer el instalador.
