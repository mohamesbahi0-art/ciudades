"""Mira en el catálogo de OpenCode qué modelo es gratis DE VERDAD y lo dice en una línea de JSON.

Solo vale uno del proveedor «opencode» (OpenCode Zen, sin cuenta ni llave), activo, que use herramientas y con TODAS
las cifras de coste a 0 (entrada, salida y caché). Se prefiere «big-pickle», el de rae por defecto. Si aparece
cualquier otro proveedor conectado, no se elige nada: querría decir que hay una llave donde no debe.

Lo lanza la caja (caja.py) dentro del contenedor, como rae, con el Python de rae y su lista cerrada de variables. Los
argumentos son los modelos que ya cobraron alguna vez (capturas.py los apunta y nunca se vuelven a usar):
  /opt/rae/bin/python -I /opt/caja/modelo.py [vetado ...]   →   {"modelo": "big-pickle", "motivo": null}
"""
import asyncio
import json
import os
import sys

import httpx2
from reverse_api.opencode_runtime import (OpenCodeSetupError, ensure_opencode_server, get_opencode_model_catalog,
                                          opencode_model_is_selectable, stop_managed_opencode_server)

PREFERIDO = "big-pickle"


def todo_cero(coste):
    if isinstance(coste, dict):
        return bool(coste) and all(todo_cero(v) for v in coste.values())
    if isinstance(coste, bool):
        return False
    return coste == 0 if isinstance(coste, (int, float)) else True


def gratis(datos):
    coste = datos.get("cost") if isinstance(datos, dict) else None
    return (opencode_model_is_selectable(datos) and isinstance(coste, dict) and coste.get("input") == 0
            and coste.get("output") == 0 and todo_cero(coste))


def elegir(catalogo, vetados=()):
    vetados = set(vetados)
    proveedores = [p for p in catalogo.get("providers") or [] if isinstance(p, dict)]
    if any(p.get("id") != "opencode" for p in proveedores):
        return None, "proveedor_extra"
    modelos = next((p.get("models") for p in proveedores if p.get("id") == "opencode"), None)
    modelos = modelos if isinstance(modelos, dict) else {}
    for nombre in sorted(modelos, key=lambda m: m != PREFERIDO):
        if nombre in vetados or f"opencode/{nombre}" in vetados:     # cobró una vez: nunca más
            continue
        if gratis(modelos[nombre]):
            return nombre, None
    return None, "sin_modelo_gratis"


async def catalogo():
    base = os.environ["OPENCODE_BASE_URL"]
    auth = httpx2.BasicAuth(os.environ.get("OPENCODE_SERVER_USERNAME", "opencode"),
                            os.environ["OPENCODE_SERVER_PASSWORD"])
    async with httpx2.AsyncClient(base_url=base, auth=auth, timeout=30.0) as cliente:
        await ensure_opencode_server(cliente, base_url=base)
        return await get_opencode_model_catalog(cliente)


def main():
    try:
        modelo, motivo = elegir(asyncio.run(catalogo()), sys.argv[1:])
    except OpenCodeSetupError:
        modelo, motivo = None, "opencode_no_arranca"
    except Exception:
        modelo, motivo = None, "sin_modelo_gratis"
    finally:
        stop_managed_opencode_server()
    print(json.dumps({"modelo": modelo, "motivo": motivo}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
