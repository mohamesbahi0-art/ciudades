"""Quita el aviso «contenido alterado o sintético» de los vídeos ya subidos (lo pidió el dueño el 26 nov).

YouTube solo lo pide para lo que parece real sin serlo (personas reales diciendo lo que no dijeron, hechos reales
inventados). Los vídeos de la fábrica son dibujos, animaciones y partidas de GTA: no hace falta. Cada cambio gasta 50
puntos de la cuota diaria de la API, así que va poco a poco (los que se publican antes, primero) y lo que haga queda
en registro/subidas.json («sin_aviso_ia»). En el registro público solo salen claves de canal y cifras.

    python herramientas/quitar_aviso_ia.py privado/registro/subidas.json [maximo]
"""
import json
import os
import sys


def main(registro, maximo=40):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    lista = json.load(open(registro, encoding="utf-8"))
    # «aviso_ia_quitado» (no el viejo «sin_aviso_ia»): la primera versión dio por hechos 20 vídeos sin cambiar ninguno,
    # porque YouTube no siempre devuelve containsSyntheticMedia al leer el vídeo.
    pendientes = [r for r in lista if r.get("id") and not r.get("aviso_ia_quitado") and r.get("ia") is not False]
    pendientes.sort(key=lambda r: str(r.get("publica") or ""))
    clientes, hechos, por_canal = {}, 0, {}
    for r in pendientes:
        if hechos >= maximo:
            break
        canal = r["canal"]
        refresh = os.environ.get("YT_REFRESH_" + canal.upper())
        if not refresh:
            continue
        if canal not in clientes:
            cred = Credentials(None, refresh_token=refresh, client_id=os.environ["YT_CLIENT_ID"],
                               client_secret=os.environ["YT_CLIENT_SECRET"], token_uri="https://oauth2.googleapis.com/token")
            clientes[canal] = build("youtube", "v3", credentials=cred, cache_discovery=False)
        yt = clientes[canal]
        try:
            items = yt.videos().list(part="status", id=r["id"]).execute().get("items", [])
            if not items:
                r["aviso_ia_quitado"] = "no está"
                continue
            st = items[0]["status"]
            if st.get("containsSyntheticMedia") is not False:     # marcado, o YouTube no lo dice: se quita igual
                nuevo = {k: st[k] for k in ("privacyStatus", "publishAt", "selfDeclaredMadeForKids", "license",
                                            "embeddable", "publicStatsViewable") if k in st}
                nuevo["containsSyntheticMedia"] = False
                yt.videos().update(part="status", body={"id": r["id"], "status": nuevo}).execute()
                hechos += 1
                por_canal[canal] = por_canal.get(canal, 0) + 1
            r["aviso_ia_quitado"] = True
        except Exception as e:
            msg = str(e)
            print(f"{canal}: no se ha podido ({type(e).__name__})")
            if "quota" in msg.lower():
                break
    json.dump(lista, open(registro, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    quedan = len([r for r in lista if r.get("id") and not r.get("aviso_ia_quitado") and r.get("ia") is not False])
    print(f"aviso de IA quitado a {hechos} vídeos {por_canal}; quedan por mirar {quedan}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40))
