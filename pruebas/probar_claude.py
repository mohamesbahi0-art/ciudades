"""Prueba de la llave de Claude (los créditos de API que trae el plan del dueño): una pregunta cortita que cuesta menos
de un céntimo, para ver que la llave vale y que la cuenta tiene créditos. El gasto y el resultado quedan en
estado/claude.json del repositorio privado; en el registro público solo sale si ha ido bien (sin cifras ni nada privado).
Se pone en marcha con peticiones/probar_claude.json.

    PRIVADO=<carpeta> ANTHROPIC_API_KEY=... python pruebas/probar_claude.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from bots.comun import claude, privado  # noqa: E402

PREGUNTA = ('Contesta SOLO este JSON, con un saludo de tres palabras en español para un creador de vídeos cortos: '
            '{"saludo": "..."}')


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Falta el secreto ANTHROPIC_API_KEY: el dueño tiene que ponerlo en GitHub (Settings → Secrets → Actions).")
        return 0
    try:
        r = claude.preguntar(PREGUNTA, "ideas", donde="prueba")
        bien, motivo = isinstance(r, dict) and bool(r.get("saludo")), ""
        print(f"Claude contesta ({claude.ULTIMO.get('modelo')}): {str(r.get('saludo'))[:40]}" if bien
              else "Claude contesta, pero sin el JSON pedido")
    except claude.NoPuede as e:
        bien, motivo = False, str(e)
        print(f"Claude no ha podido: {motivo}")
    e = privado.leer(claude.ESTADO, {}) or {}
    e["prueba"] = {"fecha": privado.ahora(), "bien": bien, "motivo": motivo, "modelo": claude.ULTIMO.get("modelo")}
    privado.guardar_estado("claude.json", e)
    print("La llave vale y hay créditos: la fábrica ya escribe con Claude." if bien else
          "Claude todavía no puede: la fábrica sigue con Gemini gratis.")
    return 0 if bien else 1


if __name__ == "__main__":
    sys.exit(main())
