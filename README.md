# @milytics/miliciano

Miliciano CLI by Milytics.

Instalación rápida del CLI:

```bash
npm install -g @milytics/miliciano
```

Comandos principales:

```bash
miliciano
miliciano home
miliciano start
miliciano day
miliciano today
miliciano about
miliciano task
miliciano tasks
miliciano jobs
miliciano status
miliciano identity
miliciano ask "..."
miliciano boundary "..."
miliciano trace
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
miliciano shell
```

Requisitos base:
- Linux
- python3
- Node.js >= 18
- npm
- curl

Qué hace cada comando:
- `miliciano` abre la home diaria de Miliciano.
- `miliciano home` y `miliciano start` muestran el panel principal con tu partner, modos y atajos de trabajo.
- `miliciano day` y `miliciano today` muestran el comando diario con prioridades, tareas y jobs vencidos.
- `miliciano about` muestra un pitch corto para explicar el producto o compartirlo.
- `miliciano task` gestiona la bandeja diaria de trabajo humano.
- `miliciano task priority` cambia la prioridad de una tarea para que el daily dashboard la ordene mejor.
- `miliciano tasks` es alias de `task`.
- `miliciano jobs` administra automatizaciones persistentes guardadas por Miliciano.
- Soporta schedules simples tipo `every 1h`, `every 30m` y cron de 5 campos tipo `0 9 * * *`.
- `miliciano jobs scheduler --once` corre los jobs vencidos una vez; `--loop` los deja corriendo en bucle como daemon ligero.
- `miliciano task` te da un inbox diario: crear, empezar, completar y cancelar tareas humanas.
- Miliciano es dueño del registro y de la intención; Hermes aporta razonamiento y OpenClaw la ejecución.
- `miliciano shell` abre el chat táctico interactivo.
- `miliciano status` muestra el estado real del stack.
- `miliciano identity` muestra o cambia el nombre, la persona y el estilo del partner.
- `miliciano ask` es la entrada principal orquestada: Miliciano decide cuándo pensar, ejecutar o activar boundary.
- `miliciano boundary` fuerza el path outward/seguro cuando quieres trabajar explícitamente sobre exposición o servicios externos.
- `miliciano trace` muestra la última decisión del orquestador, el verdict de policy y el resultado final.
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

Para personalizar la identidad del partner desde la instalación:

```bash
MILICIANO_PARTNER_NAME
MILICIANO_PERSONA
MILICIANO_OWNER_NAME
MILICIANO_LANGUAGE
MILICIANO_INTERACTION_STYLE
```

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

Instrucciones por proyecto con `MILICIANO.md`

- Si existe un archivo `MILICIANO.md` en el repo actual o en un directorio padre, Miliciano lo carga como contexto operativo del proyecto.
- Úsalo para definir idioma, estilo de respuesta, guardrails, estándares técnicos y prioridades del equipo.
- `status` muestra si el archivo fue detectado.
- Esta capa convive con la identidad del partner; la identidad define cómo habla Miliciano y `MILICIANO.md` define cómo se comporta dentro del proyecto.

Ejemplo:

```md
# MILICIANO.md

- Responde en español.
- Haz cambios mínimos y verificables.
- Explica acciones riesgosas antes de ejecutarlas.
```

Notas operativas

- El runtime principal sigue siendo el CLI Python incluido en `miliciano-poc/bin`.
- `bootstrap` y `setup --auto` priorizan instalación sin `sudo` cuando pueden.
- Para el instalador user-space de Ollama conviene tener `tar` y `zstd` disponibles.
- `doctor` omite OpenClaw si el binario no existe, en vez de romper el flujo completo.
- Miliciano enlaza `~/.hermes/.env` hacia `~/.hermes/profiles/miliciano/.env` cuando detecta que falta el `.env` del perfil.
- `install-report.json` deja trazabilidad del último bootstrap/setup para revisar qué intentó hacer el instalador.
