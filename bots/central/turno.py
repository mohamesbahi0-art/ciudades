"""Turno de un canal (o de un barrio de TikTok/Instagram) en la Ciudad Central.

El Reportero trae fuentes si el canal las necesita, el Escritor escribe, el Locutor pone la voz, el Dibujante dibuja, el
Montador monta y el Juez de guardia juzga. Después:
- canal de YouTube: el Subidor lo programa en su hueco (o lo deja en la cola si hoy no hay cupo);
- barrio: se deja en la bandeja «Para subir» con su texto para que lo suba el dueño.
Cada robot apunta en su cuaderno lo que ha hecho, y el estado queda en el repositorio privado para la app.

En los registros de GitHub (que son públicos) solo sale la clave del canal y el paso; títulos y nombres van solo al
repositorio privado.

Uso:  python bots/central/turno.py --canal terror [--hora 2026-12-01T20:00:00Z] [--prueba] [--salida carpeta]
      python bots/central/turno.py --peticion peticiones/prueba.json --prueba --salida privado/pruebas
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import shutil
import sys
import traceback

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from bots.central import dibujante, escritor, huecos, montador, parasubir, reportero, subidor  # noqa: E402
from bots.comun import privado  # noqa: E402
from bots.juzgado import sala_ideas, tribunal  # noqa: E402
import voz as locutor  # noqa: E402  (herramientas/voz.py)

ROBOTS = ("reportero_gta6", "escritor", "locutor", "dibujante", "montador", "juez_guardia", "subidor", "publicador")
# Cada canal tiene su especialista: el mismo motor, pero con su propio cuaderno (memoria) y su puesto en la app.
REPORTERO = {"gta": "reportero_gta6", "curios": "cazador_datos", "versus": "comparador"}
EN_BARRIO = {"escritor": "guionista", "montador": "editor_video"}       # en TikTok/Instagram trabajan el guionista y el editor
EN_MAPAS = {"dibujante": "dibujante_mapas", "escritor": "archivero_mapas"}


def puestos(clave, canal):
    """Qué robot hace cada paso en este canal o barrio (para su cuaderno y para la app)."""
    nombres = {r: r for r in ROBOTS}
    nombres["reportero_gta6"] = REPORTERO.get(clave, "cazador_datos" if canal["destino"] == "parasubir" else "reportero_gta6")
    if canal["destino"] == "parasubir":
        nombres.update(EN_BARRIO)
    if clave == "mapas":
        nombres.update(EN_MAPAS)
    return nombres
CON_FUENTES = ("noticias", "datos", "versus")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--canal")
    p.add_argument("--peticion")
    p.add_argument("--hora", help="hueco donde programarlo (ISO); si no se da, lo calcula")
    p.add_argument("--prueba", action="store_true", help="hace el vídeo pero no lo sube ni lo deja para subir")
    p.add_argument("--salida", default="trabajo")
    a = p.parse_args(argv)
    clave = privado.resolver(a.canal or json.load(open(a.peticion, encoding="utf-8"))["canal"])
    canal = privado.canal(clave)
    ajustes = privado.ajustes()
    hoy = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d-%H%M")
    trabajo = os.path.join(a.salida, f"{hoy}-{privado.alias(clave)}")
    os.makedirs(trabajo, exist_ok=True)
    nombres = puestos(clave, canal)
    cuadernos = {r: privado.cuaderno(nombres[r]) for r in ROBOTS}
    registro = []

    en_curso = {"robot": "escritor"}

    def paso(robot, texto, publico=None):
        if robot in cuadernos:
            en_curso["robot"] = robot
        hora = dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')
        registro.append(f"[{hora}] {robot}: {texto}")
        print(privado.limpiar(f"[{hora}] {clave} · {robot}: {publico if publico is not None else texto}"), flush=True)

    resumen = {"canal": clave, "nombre": canal["nombre"], "destino": canal["destino"], "prueba": a.prueba,
               "empezado": privado.ahora()}
    try:
        fuentes, lista = None, []
        if canal.get("tipo") in CON_FUENTES and canal.get("fuentes"):
            paso("reportero_gta6", "buscando fuentes")
            fuentes, lista = reportero.fuentes(clave, canal, registro=lambda t: paso("reportero_gta6", t))
            if not fuentes:
                raise RuntimeError("el Reportero no ha encontrado ninguna fuente hoy")
            cuadernos["reportero_gta6"].apuntar("fuentes", {"canal": clave, "cuantas": len(lista)})
            paso("reportero_gta6", f"{len(lista)} fuentes")

        receta = (privado.leer(os.path.join("estado", "influencers", "recetas.json"), {}) or {}).get("canales", {}).get(clave)
        lecciones_escritor = cuadernos["escritor"].para_el_prompt()
        if receta:                               # la receta de los Influencers para este canal
            lecciones_escritor += "\n- (Receta de los Influencers, de lo que funciona ahora) " + json.dumps(
                {k: v for k, v in receta.items() if k not in ("fecha", "basada_en")}, ensure_ascii=False)
        idea, id_idea = None, None
        if ajustes.get("sala_ideas", True):     # la Sala de Ideas elige la mejor de 3 antes de gastar dibujos
            paso("escritor", "proponiendo ideas a la Sala de Ideas")
            try:
                propuestas = escritor.ideas(canal, lecciones_escritor, privado.titulos_recientes(clave), fuentes)
                idea, id_idea = sala_ideas.elegir(clave, canal, propuestas, tribunal._pruebas(clave, canal))
                paso("escritor", f"la Sala de Ideas eligió «{(idea or {}).get('titulo')}» de {len(propuestas)}",
                     f"la Sala de Ideas eligió 1 de {len(propuestas)}")
            except Exception as e:      # sin Sala de Ideas, el Escritor sigue solo
                paso("escritor", f"sin Sala de Ideas hoy ({type(e).__name__})")
        aviso_juez = ""
        for intento in (1, 2):           # si el Juez lo suspende, una segunda oportunidad con su consejo
            if intento == 2:
                paso("escritor", "segunda oportunidad: lo reescribe con el consejo del Juez")
            paso("escritor", "escribiendo el guion")
            g = escritor.escribir(canal, lecciones_escritor + aviso_juez,
                                 privado.titulos_recientes(clave), fuentes, idea=idea)
            if lista:
                reportero.apuntar_usadas(clave, lista, g.get("fuentes_usadas"))
            json.dump(g, open(os.path.join(trabajo, "guion.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            id_guion = cuadernos["escritor"].apuntar("guion", {"canal": clave, "titulo": g["titulo"], "idea": g.get("idea"),
                                                               "prueba": a.prueba})
            paso("escritor", f"«{g['titulo']}» ({len(g['escenas'])} escenas)", f"guion listo ({len(g['escenas'])} escenas)")

            paso("locutor", f"grabando la voz ({canal.get('voz')})")
            asyncio.run(locutor.generar(g["narracion"], canal.get("voz", "es-MX-JorgeNeural"), canal.get("velocidad", "+10%"),
                                        "+0Hz", trabajo))
            quitado = locutor.apretar(trabajo)
            cuadernos["locutor"].apuntar("voz", {"canal": clave, "guion": id_guion, "silencio_quitado": quitado})
            paso("locutor", f"voz lista ({quitado} s de silencios quitados)")

            paso("dibujante", f"pidiendo {len(g['escenas'])} dibujos a AI Horde ({canal.get('dibujos')})")
            t0 = dt.datetime.now(dt.timezone.utc)
            imagenes = dibujante.dibujar(g["escenas"], canal.get("dibujos", "AlbedoBase XL (SDXL)"),
                                         os.path.join(trabajo, "dibujos"))
            faltan = imagenes.count(None)
            minutos = round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds() / 60, 1)
            cuadernos["dibujante"].apuntar("dibujos", {"canal": clave, "pedidos": len(imagenes), "faltan": faltan,
                                                       "minutos": minutos})
            if faltan > max(1, len(imagenes) // 3):
                raise RuntimeError(f"faltan {faltan} dibujos de {len(imagenes)}")
            paso("dibujante", f"{len(imagenes) - faltan}/{len(imagenes)} dibujos hechos en {minutos} min")

            paso("montador", "montando el vídeo")
            video = montador.montar(g, imagenes, os.path.join(trabajo, "voz.mp3"), os.path.join(trabajo, "palabras.json"),
                                    os.path.join(trabajo, f"{hoy}-{clave}.mp4"))  # nombre único: el registro lo usa
            segundos = montador.duracion(video)
            cuadernos["montador"].apuntar("montaje", {"canal": clave, "guion": id_guion, "segundos": round(segundos, 1)})
            paso("montador", f"vídeo de {segundos:.1f} s")

            paso("juez_guardia", "juzgando el vídeo")
            v = tribunal.juzgar(video, g, canal, cuadernos["juez_guardia"].para_el_prompt(),
                                os.path.join(trabajo, f"juicio{intento}"))
            id_tribunal = tribunal.guardar_juicio(clave, g, v, prueba=a.prueba)
            id_juicio = cuadernos["juez_guardia"].apuntar("juicio", {"canal": clave, "guion": id_guion,
                                                                     "veredicto": v["veredicto"], "total": v.get("total")})
            cuadernos["escritor"].nota(id_guion, v.get("total"), "nota del Juez de guardia", v.get("consejo", ""))
            paso("juez_guardia", f"{v['veredicto']} ({v.get('total', '-')}/100) {v.get('consejo', '')}",
                 f"{v['veredicto']} ({v.get('total', '-')}/100)")
            resumen.update(titulo=g["titulo"], veredicto=v["veredicto"], nota=v.get("total"), consejo=v.get("consejo"),
                           juicio=id_juicio, segundos=round(segundos, 1), intento=intento,
                           fallos=v.get("fallos_graves"), tribunal=v.get("tribunal"), juicio_app=id_tribunal,
                           juicio_idea=id_idea)
            if v["veredicto"] != "suspendido" or a.prueba or not ajustes.get("segunda_oportunidad", True):
                break
            aviso_juez = (f"\n- (Juez de guardia, sobre la versión anterior, suspendida con {v.get('total', '-')}/100) "
                          f"{v.get('consejo', '')} Fallos: {', '.join(v.get('fallos_graves') or []) or 'ninguno grave'}. "
                          "Escribe un guion distinto que lo corrija.")

        if a.prueba:
            paso("subidor", "es una prueba: no se sube nada")
            resumen["destino_resultado"] = "prueba"
        elif v["veredicto"] == "suspendido":
            paso("subidor", "el Juzgado lo ha suspendido: no se sube")
            resumen["destino_resultado"] = "suspendido"
        elif canal["destino"] == "parasubir":
            ids = parasubir.dejar(clave, canal, video, g, segundos, v)
            cuadernos["publicador"].apuntar("para_subir", {"barrio": clave, "documentos": ids, "guion": id_guion})
            privado.apuntar_titulo(clave, g["titulo"])
            paso("publicador", f"en la bandeja «Para subir»: {', '.join(ids)}", f"en la bandeja ({len(ids)} redes)")
            resumen.update(destino_resultado="para_subir", documentos=ids)
        else:
            hora = huecos.fecha(a.hora) if a.hora else None
            if not hora:
                registro_subidas = privado.leer(subidor.REGISTRO, []) or []
                revision = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {})
                cola = subidor.en_cola()
                hora = huecos.siguiente(canal["horas"], huecos.ocupados(revision, registro_subidas, cola, clave),
                                        dias_maximos=ajustes["dias_maximos"])
            if hora and subidor.hay_cupo(ajustes):
                r = subidor.subir(clave, canal, video, g, hora)
                paso("subidor", f"{r['resultado']}: {r['mensaje']}", f"{r['resultado']} (código {r['codigo']})")
                resumen.update(destino_resultado=r["resultado"], hora=r.get("hora"), url=r.get("url"))
                cuadernos["subidor"].apuntar("subida", {"canal": clave, "guion": id_guion, "codigo": r["codigo"],
                                                        "hora": r.get("hora"), "video": r.get("id")})
                if r["resultado"] != "subido":
                    nombre = subidor.encolar(clave, video, g, r["mensaje"], v)
                    paso("subidor", f"guardado en la cola: {nombre}", "guardado en la cola")
                    resumen.update(destino_resultado="en_cola", motivo=r["mensaje"], codigo=r["codigo"])
            else:
                motivo = "no hay hueco en los próximos días" if not hora else "hoy no queda cupo de subidas"
                nombre = subidor.encolar(clave, video, g, motivo, v)
                paso("subidor", f"{motivo}: guardado en la cola ({nombre})", f"{motivo}: guardado en la cola")
                resumen.update(destino_resultado="en_cola", motivo=motivo)
        resumen["resultado"] = "hecho"
    except Exception as e:  # el turno nunca se queda a medias sin contarlo
        resumen.update(resultado="error", error=f"{type(e).__name__}: {e}", robot=nombres[en_curso["robot"]])
        cuadernos[en_curso["robot"]].apuntar("error", {"canal": clave, "error": f"{type(e).__name__}: {str(e)[:300]}"})
        paso("turno", f"ERROR {type(e).__name__}: {e}", f"ERROR {type(e).__name__}")
        detalle = traceback.format_exc()
        with open(os.path.join(trabajo, "fallo.txt"), "w", encoding="utf-8") as f:
            f.write(detalle)
        resumen["traza"] = detalle[-2000:]
        print(privado.limpiar("\n".join(detalle.strip().splitlines()[-12:])), flush=True)
    finally:
        resumen["terminado"] = privado.ahora()
        with open(os.path.join(trabajo, "registro.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(registro) + "\n")
        json.dump(resumen, open(os.path.join(trabajo, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for c in cuadernos.values():
            c.guardar()
        historial = (privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}).get("turnos", [])
        historial = (historial + [resumen])[-20:]
        privado.guardar_estado(f"central/{clave}.json", {"canal": clave, "ultimo_turno": resumen, "turnos": historial})
        shutil.rmtree(os.path.join(trabajo, "dibujos", "tmp"), ignore_errors=True)
    return 0 if resumen.get("resultado") == "hecho" else 1


if __name__ == "__main__":
    sys.exit(main())
