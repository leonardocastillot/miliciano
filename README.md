# @milytics/miliciano

Miliciano CLI by Milytics.

Instalación:

```bash
npm install -g @milytics/miliciano
```

Uso:

```bash
miliciano
miliciano status
miliciano setup
miliciano doctor
miliciano think "..."
miliciano exec "..."
miliciano mission "..."
```

Requisitos:
- Linux
- python3
- Node.js >= 18 para el wrapper npm

Notas:
- El comando `miliciano` abre la consola interactiva.
- Si se ejecuta sin argumentos, muestra el banner de arranque.
- El runtime principal sigue siendo el CLI Python incluido en `miliciano-poc/bin`.
