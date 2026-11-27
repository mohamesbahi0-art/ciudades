"""Arranca el programa de la IA con el vigilante puesto (dentro de la caja, en el Python limpio y con -I).

  /opt/cliente/bin/python -I -X utf8 /opt/caja/arranque.py <cliente.py> <cuenta.json> [vigilante.json]
"""
import os
import runpy
import sys

sys.path.append("/opt/caja")
import vigilante  # noqa: E402

programa, cuenta = sys.argv[1], sys.argv[2]
reglas = sys.argv[3] if len(sys.argv) > 3 else ""
vigilante.poner(reglas, os.environ["CAJA_DOMINIO"], cuenta)
sys.argv = [programa]
runpy.run_path(programa, run_name="__main__")
