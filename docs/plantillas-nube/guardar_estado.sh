#!/usr/bin/env bash
# Guarda en el repositorio el estado que han dejado los bots (carpeta estado/), sin pisar a los demás carriles.
# Va en bots/comun/guardar_estado.sh. Uso: bash guardar_estado.sh "quién guarda"
set -u
git config user.name "ciudades-bot"
git config user.email "ciudades-bot@users.noreply.github.com"
git add estado/ registro/ 2>/dev/null || true
if git diff --cached --quiet; then echo "Nada nuevo que guardar."; exit 0; fi
git commit -q -m "estado: $1"
for intento in 1 2 3 4 5; do
  if git pull -q --rebase && git push -q; then echo "Estado guardado."; exit 0; fi
  sleep $((intento * 7))
done
echo "No pude guardar el estado tras 5 intentos." >&2
exit 1
