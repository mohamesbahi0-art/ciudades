"""La ronda de la fábrica: lo que hace GitHub cada dos horas, sin Claude y sin ningún ordenador encendido.

1. El Subidor intenta subir lo que esperaba en la cola.
2. El Organizador decide qué canales y barrios necesitan vídeo: primero los que tienen menos días de vídeos por delante
   (los vacíos antes que nadie), solo después de su último vídeo programado y nunca a más de un mes.
3. Hace un turno por cada uno (turno.py) y guarda lo hecho en el repositorio privado después de cada vídeo.

Se para sola si hoy no queda cupo de subidas y la cola ya está llena, para no hacer vídeos que no se pueden subir.

Uso:  python bots/central/fabrica.py [--prueba] [--solo gta,curios] [--maximo 2]
"""
import argparse
import datetime as dt
import os
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
from bots.central import a_mano  # noqa: E402
from bots.central import clips, discoteca, huecos, parasubir, subidor, turno, videoteca  # noqa: E402
from bots.comun import privado  # noqa: E402

SIN_HACER = {}                   # tipos de canal que todavía no se pueden hacer (y por qué)
SOLO_CON_CLIP = ("clips",)       # canales que solo trabajan cuando el dueño ha grabado un clip para ellos
ESPERA_DUENO = 30 * 60           # «Juzga mi vídeo» va primero: como mucho media hora de pausa por vídeo del dueño
YA_ESPERADOS = set()


def revisiones(cfg):
    return {k: privado.leer(os.path.join("estado", "canales", f"{k}.json"), {}) or {} for k in cfg.get("canales", {})}


# Cuatro equipos a la vez (el dueño: «donde más se sature, duplicamos»): los canales de YouTube que dibujan (lo más
# lento: el servicio gratis de dibujos tarda hasta media hora por vídeo), el resto de canales (animados y de clips) y
# las cuentas de TikTok/Instagram repartidas en dos, para que ninguna espere a que acabe otra. Cada equipo lleva su
# propio turno por el Jurado, el Juzgado y el Coliseo.
LINEAS = ("canales", "dibujos", "cuentas", "cuentas2")


def de_linea(linea, clave, c, cfg):
    """¿Este canal o barrio lo hace esta línea? (sin línea, todos)."""
    if not linea:
        return True
    if clave in (cfg.get("barrios") or {}):
        activos = [k for k, b in cfg["barrios"].items() if b.get("estado") == "activo"]
        par = (activos.index(clave) % 2 == 0) if clave in activos else True
        return linea == ("cuentas" if par else "cuentas2")
    dibuja = c.get("estudio") != "animacion" and not c.get("solo_clips") and c.get("tipo") != "clips" and clave != "clips"
    return linea == ("dibujos" if dibuja else "canales")


def fichero(linea=None):
    """Dónde apunta su ronda cada línea (la de canales, en el de siempre, que es el que lee la app)."""
    return "fabrica.json" if linea in (None, "canales") else f"fabrica-{linea}.json"


def planear(ajustes, cfg, revs, solo=None, ahora=None, linea=None):
    """Devuelve [(clave, hora o None, motivo)] por orden de urgencia, y lo que se queda sin hacer y por qué."""
    ahora = ahora or dt.datetime.now(dt.timezone.utc)
    registro = privado.leer(subidor.REGISTRO, []) or []
    cola = subidor.en_cola()
    cupo = subidor.hay_cupo(ajustes)
    cola_llena = len(cola) >= ajustes["cola_maxima"]
    orden = {k: i for i, k in enumerate(ajustes.get("prioridad", []))}
    candidatos, esperan = [], {}
    hoy = ahora.strftime("%Y-%m-%d")
    fallidos = {}
    for r in (privado.leer(os.path.join("estado", fichero(linea)), {}) or {}).get("rondas", []):
        if str(r.get("empezada", "")).startswith(hoy) and not r.get("prueba"):
            for t in r.get("turnos", []):
                if t.get("destino") == "suspendido":
                    fallidos[t.get("canal")] = fallidos.get(t.get("canal"), 0) + 1
    tope = int(ajustes.get("intentos_fallidos_dia", 2))
    lejos = int(ajustes.get("intentos_si_va_lejos", 2))     # un formato que no pasa de 80 no gasta 6 intentos al día
    try:
        con_clip = clips.canales_con_clips()     # los clips que ha grabado el dueño van antes que nada
    except Exception:
        con_clip = set()

    cada_lejos = float(ajustes.get("horas_si_va_lejos", 2))   # el que va lejos de la nota mínima no para: lo intenta cada 2 horas

    def pendiente(clave):
        """¿Tiene un vídeo que se quedó cerca de la nota y espera su versión corregida? Eso va antes que nada."""
        try:
            return bool(turno.arreglo_pendiente(clave))
        except Exception:
            return False

    de_primera = []                   # ¿hay juez de primera ahora? Se mira una vez, y solo si hace falta

    def hay_juez_de_primera():
        if not de_primera:
            try:
                from bots.comun import ia
                de_primera.append(bool(ia.hay_de_primera("juez")))
            except Exception:
                de_primera.append(True)
        return de_primera[0]

    def insiste(clave):
        hechos = fallidos.get(clave, 0)
        try:                          # vídeos que un juez suplente dio por buenos y esperan al juez de primera
            from bots.juzgado import espera as sala_espera
            en_sala, llena = sala_espera.cuantos(clave), sala_espera.llena(clave)
        except Exception:
            en_sala, llena = 0, False
        if en_sala and hay_juez_de_primera():
            return True               # confirmar lo que espera va antes que nada y no gasta intentos
        if llena:
            esperan[clave] = (f"tiene {en_sala} vídeos en la Sala de espera (un juez suplente los dio por buenos): "
                              "espera a que haya juez de primera para confirmarlos")
            return False
        if pendiente(clave):          # un arreglo pendiente se salta el tope normal y la espera, pero no un tope duro
            if hechos >= tope * 2:
                esperan[clave] = (f"hoy ya lleva {hechos} turnos sin llegar al 90, también con arreglos: mañana sigue "
                                  "con el que tiene pendiente")
                return False
            return True
        if hechos >= tope:
            esperan[clave] = f"hoy ya lo ha intentado {hechos} veces sin llegar a la nota mínima: mañana más"
            return False
        mejor = mejor_nota(clave)
        if hechos >= lejos and mejor is not None and mejor < privado.nota_minima() - 10:
            ultimo = ((privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {})
                      .get("ultimo_turno") or {}).get("terminado")
            try:
                hace = (ahora - huecos.fecha(ultimo)).total_seconds() / 3600 if ultimo else cada_lejos
            except (TypeError, ValueError):
                hace = cada_lejos
            if hace < cada_lejos:
                esperan[clave] = (f"hoy lo ha intentado {hechos} veces y su mejor nota es {mejor}: mientras vaya lejos "
                                  f"del 90 lo intenta cada {cada_lejos:g} horas en vez de cada ronda (no se gasta IA en balde)")
                return False
        return True
    try:                                      # lo que han decidido los Mecánicos (canales descansando, dibujos caídos)
        from bots.mecanicos import taller
        estado_taller = taller.leer()
    except Exception:
        taller, estado_taller = None, {}

    def descansa(clave, dibuja=False):
        if not taller:
            return False
        motivo = taller.en_cuarentena(clave, estado_taller, ahora)
        if not motivo:                       # la Élite puede tener la cuenta en reforma
            try:
                from bots.elite import elite
                motivo = elite.en_reforma(clave, ahora=ahora)
            except Exception:
                motivo = None
        if not motivo and dibuja and taller.dibujos_caidos(estado_taller, ahora):
            motivo = "el servicio gratis de dibujos está caído: los mecánicos lo han dejado esperar unas horas"
        if motivo:
            esperan[clave] = motivo
        return bool(motivo)

    for clave, c in cfg.get("canales", {}).items():
        if (solo and clave not in solo) or not de_linea(linea, clave, c, cfg):
            continue
        if c.get("pausado"):
            esperan[clave] = "en pausa"
            continue
        animado = int((privado.cambios_elite()["canales"].get(clave) or {}).get("hipnotico_cada")
                      or c.get("hipnotico_cada") or 0) == 1          # el Cerebro la ha pasado al formato sin dibujos
        if descansa(clave, dibuja=c.get("estudio") != "animacion" and not c.get("solo_clips") and not animado):
            continue
        if (c.get("tipo") in SOLO_CON_CLIP or clave in SOLO_CON_CLIP) and clave not in con_clip:
            esperan[clave] = "esperando a que grabes un clip (la lista está en la app)"
            continue
        if c.get("tipo") in SIN_HACER or clave in SIN_HACER:
            esperan[clave] = SIN_HACER.get(c.get("tipo"), SIN_HACER.get(clave))
            continue
        if not os.environ.get(f"YT_REFRESH_{clave.upper()}"):
            esperan[clave] = "sin permiso de YouTube"
            continue
        if c.get("solo_clips") and not videoteca.suficientes(dict(c, clave=clave)):   # el dueño no quiere fotos en GTA
            lista = videoteca.disponibles(dict(c, clave=clave))
            esperan[clave] = (f"espera clips de juego de verdad (hay {len(lista)} tomas; hacen falta "
                              f"{videoteca.MIN_TOMAS} de {videoteca.MIN_FUENTES} vídeos, o {videoteca.MIN_PAREJAS} parejas "
                              "GTA 5/GTA 6): el Recolector las trae cada día. Nada de vídeos con fotos")
            continue
        if not cupo and cola_llena:
            esperan[clave] = "hoy no queda cupo de subidas y la cola está llena"
            continue
        ocupadas = huecos.ocupados(revs.get(clave), registro, cola, clave)
        hora = huecos.siguiente(c["horas"], ocupadas, ahora=ahora, dias_maximos=ajustes["dias_maximos"])
        if not hora:
            esperan[clave] = f"ya tiene vídeos para {ajustes['dias_maximos']} días"
            continue
        if insiste(clave):
            candidatos.append((not pendiente(clave), clave not in con_clip, huecos.colchon(ocupadas, ahora),
                               orden.get(clave, 99), clave, hora))
    for clave, b in cfg.get("barrios", {}).items():
        if (solo and clave not in solo) or not de_linea(linea, clave, b, cfg):
            continue
        if b.get("estado") != "activo":
            esperan[clave] = b.get("motivo") or "en pausa"
            continue
        if descansa(clave):
            continue
        pend = [d for d in parasubir.documentos() if d.get("barrio") == clave and d.get("estado") == "pendiente"]
        if len({d.get("titulo") for d in pend}) >= ajustes["pendientes_por_barrio"]:
            esperan[clave] = f"ya tiene {ajustes['pendientes_por_barrio']} vídeos esperando a que los subas"
            continue
        fechas = [huecos.fecha(d["cuando"]) for d in pend if d.get("cuando")]
        dias = max(0.0, (max(fechas) - ahora).total_seconds() / 86400) if fechas else 0.0
        if dias > 1.5:
            esperan[clave] = "tiene vídeos para los próximos días"
            continue
        if insiste(clave):
            candidatos.append((not pendiente(clave), clave not in con_clip, dias, orden.get(clave, 99), clave, None))
    candidatos.sort()
    return [(clave, hora) for *_, clave, hora in candidatos], esperan


def mejor_nota(clave, cuantos=6):
    """La mejor nota de los últimos juicios de vídeo de un canal (hoy y ayer). None si no hay ninguno."""
    import glob
    import json
    hoy = dt.datetime.now(dt.timezone.utc)
    notas = []
    for dia in (hoy - dt.timedelta(days=1), hoy):
        patron = os.path.join(privado.carpeta(), "estado", "juzgado", "juicios", f"{dia.strftime('%Y%m%d')}-*.json")
        for ruta in sorted(glob.glob(patron)):
            if ruta.endswith(("-idea.json", "-jurado.json")):
                continue
            try:
                j = json.load(open(ruta, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if j.get("canal") == clave and j.get("tipo") == "video" and isinstance(j.get("nota"), (int, float)):
                notas.append(j["nota"])
    return max(notas[-cuantos:]) if notas else None


def hay_ia(arreglo=False, solo_claude=False):
    """¿Hay con qué hacer un vídeo ahora? Hace falta quien escriba (Claude con presupuesto para esta hora, o la IA
    gratis contestando) Y quien juzgue (Claude, Gemini de primera o, si no, un juez suplente de la IA gratis de
    reserva: lo que el suplente dé por bueno espera en la Sala de espera al juez de primera): sin juez, el vídeo se
    haría para nada, porque nada sale sin juicio. `arreglo`: el turno empieza por la versión corregida de un vídeo
    (tiene su propio presupuesto, por delante del de los guiones nuevos). Devuelve (sí o no, a quién le falta)."""
    from bots.comun import claude, gemini
    escribe = juzga = False
    try:
        escribe = claude.puede("guionista") or (arreglo and claude.puede("arreglo"))
    except Exception:
        pass
    if not escribe and solo_claude:          # esta cuenta solo la escribe Claude: sin su presupuesto, espera ELLA
        return False, "claude"               # (las demás cuentas de la línea siguen con la IA gratis)
    if not escribe:
        try:
            gemini.preguntar("Contesta solo con la palabra OK.", json_salida=False, intentos=1, ligero_primero=True,
                             paciencia=1)
            escribe = True
        except Exception:
            escribe = False
    if not escribe:
        return False, "escritor"
    try:
        juzga = claude.puede("juez", a_su_hora=True)     # a su hora: no se empiezan más vídeos de los que el día puede juzgar
    except Exception:
        pass
    if not juzga:
        try:
            juzga = not gemini.primera_agotada()         # Gemini de primera: se sabe por la última ronda, sin preguntar
        except Exception:
            juzga = False
    if not juzga:
        try:        # los suplentes gratis: suspenden y mandan arreglar; lo que den por bueno espera al juez de primera
            gemini.preguntar("Contesta solo con la palabra OK.", json_salida=False, intentos=1, solo_bueno=True,
                             paciencia=0, fila="segunda")
            juzga = True
        except Exception:
            juzga = False
    return (True, "") if juzga else (False, "juez")


def pausa_sin_ia(quien=""):
    """Apunta la pausa para la app: por qué está parada la fábrica y hasta cuándo (cuando la IA de pago vuelve a tener
    su parte; la gratis puede volver antes y entonces la pausa se quita sola)."""
    from bots.central import obras
    from bots.comun import claude
    try:
        hasta = claude.cuando_puede("juez" if quien == "juez" else "guionista")
    except Exception:
        hasta = None
    motivo = ("No queda quien juzgue los vídeos ahora: ni la IA gratis que ve imágenes (tampoco la de reserva) ni la de "
              "pago pueden a esta hora." if quien == "juez" else
              "La IA gratis está saturada y la de pago ya ha gastado su parte de esta hora.")
    obras.pausar(motivo + " Lo que estaba a medias no se pierde: sigue solo en cuanto vuelva.", hasta)


de_fuera = turno.de_fuera        # fallos que no son del código: la IA sin cupo o el servicio gratis de dibujos caído


def atender_al_dueno(paso=print, guardar=None):
    """Si el dueño ha subido un vídeo («Juzga mi vídeo»), la fábrica lo juzga en este momento, sin esperar a su turno
    de GitHub (que puede tardar una hora). Devuelve los segundos que ha tardado (no le quitan tiempo a la cola)."""
    t0 = time.time()
    try:
        from bots.juzgado import ventanilla
        if not ventanilla.ramas():
            return 0.0
        paso("hay un vídeo del dueño: se juzga ahora mismo, antes que la cola")
        ventanilla.main([])
        if guardar:
            guardar("fábrica: vídeo del dueño juzgado")
    except SystemExit:
        pass
    except Exception as e:
        paso(f"el vídeo del dueño no se ha podido juzgar aquí ({type(e).__name__}): lo hará su turno")
    return time.time() - t0


def espera_del_dueno(paso=print, cada=60):
    """Los vídeos que sube el dueño en «Juzga mi vídeo» van antes que todo: si hay uno en el Juzgado (su rama
    juicio/<codigo> sigue viva), la fábrica para hasta que termine y luego sigue con la cola. Como mucho media hora por
    vídeo, por si algo se atasca. Devuelve los segundos que ha esperado."""
    try:
        from bots.juzgado import ventanilla
    except Exception:
        return 0.0
    inicio, avisado = time.time(), False
    while True:
        try:
            pendientes = set(ventanilla.ramas()) - YA_ESPERADOS
        except Exception:
            return time.time() - inicio
        if not pendientes:
            if avisado:
                paso("el vídeo del dueño ya está juzgado: la fábrica sigue con la cola")
            return time.time() - inicio
        if time.time() - inicio > ESPERA_DUENO:
            YA_ESPERADOS.update(pendientes)
            paso("el vídeo del dueño tarda más de media hora: la fábrica sigue y él se juzga a la vez")
            return time.time() - inicio
        if not avisado:
            paso(f"pausa: hay {len(pendientes)} vídeo(s) del dueño en el Juzgado; la fábrica espera a que terminen")
            avisado = True
        time.sleep(cada)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", help="planea y hace los vídeos, pero no sube ni guarda nada")
    p.add_argument("--solo", help="claves separadas por comas")
    p.add_argument("--maximo", type=int)
    p.add_argument("--sin-guardar", action="store_true")
    p.add_argument("--linea", choices=LINEAS, help="solo los canales de YouTube o solo las cuentas de TikTok/Instagram")
    a = p.parse_args()
    inicio = time.time()
    ajustes, cfg = privado.ajustes(), privado.config()
    solo = {privado.resolver(x) for x in a.solo.split(",")} if a.solo else None
    maximo = a.maximo or ajustes["videos_por_ronda"]
    revs = revisiones(cfg)
    rondas = (privado.leer(os.path.join("estado", fichero(a.linea)), {}) or {}).get("rondas", [])
    tareas = a.linea in (None, "canales")    # la cola, la videoteca y la limpieza las hace la línea de canales
    ronda = {"empezada": privado.ahora(), "prueba": a.prueba, "turnos": []}
    trabajo = tempfile.mkdtemp(prefix="fabrica-")

    def guardar(mensaje):
        if not a.prueba and not a.sin_guardar:
            privado.git_guardar(mensaje)

    if not a.prueba and a.linea in (None, "canales", "dibujos"):
        mios = None if not a.linea else (lambda k: de_linea(a.linea, k, (cfg.get("canales") or {}).get(k) or {}, cfg))
        subidos = subidor.vaciar_cola(ajustes, revs, trabajo, solo=mios)
        ronda["cola_subidos"] = subidos
        if subidos:
            print(f"cola: {subidos} vídeo(s) subidos", flush=True)
            guardar(f"fábrica: {subidos} vídeo(s) de la cola subidos")

    if not a.prueba and tareas:
        try:                                    # el Archivero: los clips grabados, limpios a la videoteca
            guardados = videoteca.archivar(paso=lambda t: print(privado.limpiar(t), flush=True))
            repasadas = videoteca.repasar_marcas(paso=lambda t: print(privado.limpiar(t), flush=True))
            if guardados or repasadas:
                guardar(f"videoteca: {guardados} toma(s) nuevas y {repasadas} sin logos")
        except Exception as e:
            print(f"videoteca: el Archivero no ha podido trabajar ({type(e).__name__})", flush=True)

    if not a.prueba and tareas:
        try:
            ramas = clips.limpiar_ramas()       # las ramas temporales de clips ya usados o descartados
            if ramas:
                print(f"buzón de clips: {ramas} rama(s) temporales borradas", flush=True)
        except Exception as e:
            print(f"buzón de clips: no he podido limpiar ({type(e).__name__})", flush=True)

    if not a.prueba and tareas:
        try:
            borrados = parasubir.limpiar()     # la estantería «para-subir» no crece sin fin
            if borrados:
                print(f"almacén: {borrados} vídeo(s) ya subidos borrados de la estantería", flush=True)
        except Exception as e:
            print(f"almacén: no he podido limpiar ({type(e).__name__})", flush=True)

    try:                                       # música de verdad (dominio público) para los vídeos de esta ronda
        piezas = discoteca.preparar(os.path.join(trabajo, "musica"))
        print(f"discoteca: {piezas} piezas de música libre listas" if piezas else "discoteca: sin piezas, se compone",
              flush=True)
    except Exception as e:
        print(f"discoteca: sin música libre ({type(e).__name__}); se compone", flush=True)

    plan, esperan = planear(ajustes, cfg, revs, solo, linea=a.linea)
    ronda["plan"] = [k for k, _ in plan][:maximo]
    ronda["esperan"] = esperan
    barrios_hoy = [k for k in ronda["plan"] if k in cfg.get("barrios", {})]
    if barrios_hoy:                          # el Robot del vídeo diario prepara el vídeo de cada barrio
        diario = privado.cuaderno("robot_video_diario")
        for k in barrios_hoy:
            diario.apuntar("video_del_dia", {"barrio": k})
        diario.guardar()
    organizador = privado.cuaderno("organizador")
    organizador.apuntar("ronda", {"plan": ronda["plan"], "esperan": esperan, "prueba": a.prueba})
    organizador.guardar()
    print(privado.limpiar(f"plan: {', '.join(map(privado.alias, ronda['plan'])) or 'nada que hacer'}"), flush=True)
    for clave, motivo in esperan.items():
        print(privado.limpiar(f"  {privado.alias(clave)}: {motivo}"), flush=True)

    # los que necesitaban vídeo y no han cabido en esta ronda (la Jefa de Máquinas avisa si pasa a menudo)
    ronda["sin_sitio"] = [k for k, _ in plan[maximo:]]
    sin_ia = 0                       # turnos seguidos en los que la IA no ha contestado
    for clave, hora in plan[:maximo]:
        if not a.prueba:             # lo del dueño, primero: su vídeo se juzga aquí mismo, antes que la cola
            inicio += atender_al_dueno(paso=lambda t: print(t, flush=True), guardar=guardar)
            inicio += espera_del_dueno(paso=lambda t: print(t, flush=True))   # la espera no le quita tiempo a la cola
        if (time.time() - inicio) / 60 > ajustes["minutos_por_ronda"]:
            print("se acaba el tiempo de la ronda: lo que falta, en la siguiente", flush=True)
            ronda["sin_sitio"] += [k for k, _ in plan[:maximo] if k not in {t["canal"] for t in ronda["turnos"]}]
            break
        try:
            con_arreglo = bool(turno.arreglo_pendiente(clave))
        except Exception:
            con_arreglo = False
        try:
            solo_claude = privado.canal(clave).get("guionista") == "claude"
        except BaseException:
            solo_claude = False
        try:                                     # con un guion escrito a mano, no hace falta quien escriba: solo jueces
            if a_mano.cuantos(clave):
                solo_claude, con_arreglo = False, False
        except Exception:
            pass
        con_ia, falta = (True, "") if a.prueba else hay_ia(arreglo=con_arreglo, solo_claude=solo_claude)
        if not con_ia and falta == "claude":     # cosa de esta cuenta, no de la fábrica: ni se corta la línea ni hay pausa
            ronda["esperan"][clave] = ("solo escribe con el cerebro de pago (lo decidió la Élite) y ahora no tiene su "
                                       "parte de esta hora: lo intenta en la siguiente ronda")
            print(privado.limpiar(f"  {privado.alias(clave)}: espera al cerebro de pago; la línea sigue"), flush=True)
            continue
        if con_ia and not a.prueba:  # hay con qué trabajar: fuera la pausa de la app (si la había)
            from bots.central import obras
            obras.reanudar()
        if not con_ia:               # sin IA no se empieza un turno (no se gastan voz, dibujos ni intentos)
            hechos = {t["canal"] for t in ronda["turnos"]}
            for k, _ in plan[:maximo]:
                if k not in hechos:
                    ronda["esperan"][k] = ("no hay quien juzgue ahora (la IA ha gastado su parte): lo intenta en la "
                                           "siguiente ronda" if falta == "juez" else
                                           "la IA no tiene cupo a esta hora: lo intenta en la siguiente ronda")
            print("no queda IA para esta hora" + (" (falta el juez)" if falta == "juez" else "")
                  + ": lo que falta, en la siguiente ronda", flush=True)
            pausa_sin_ia(falta)
            break
        if sin_ia:                   # la IA estaba saturada: un respiro antes del siguiente turno, en vez de perderlo
            respiro = int(ajustes.get("respiro_ia_segundos", 180))
            print(f"la IA no contestaba: espero {respiro // 60} min antes del siguiente turno", flush=True)
            time.sleep(respiro)
        args = ["--canal", clave, "--salida", trabajo] + (["--hora", huecos.iso(hora)] if hora else [])
        if a.prueba:
            args.append("--prueba")
        codigo = turno.main(args)
        estado = privado.leer(os.path.join("estado", "central", f"{clave}.json"), {}) or {}
        ultimo = estado.get("ultimo_turno", {})
        ronda["turnos"].append({"canal": clave, "codigo": codigo, "resultado": ultimo.get("resultado"),
                                "destino": ultimo.get("destino_resultado"), "error": ultimo.get("error")})
        privado.guardar_estado(fichero(a.linea), dict(ronda, linea=a.linea, cuota=subidor.cuota(), cola=len(subidor.en_cola()),
                                                    rondas=rondas))
        guardar(f"fábrica: turno de {clave} ({ultimo.get('destino_resultado') or ultimo.get('resultado')})")
        sin_ia = sin_ia + 1 if codigo != 0 and str(ultimo.get("error") or "").startswith("SinIA") else 0
        if not a.prueba:             # la pausa de la app: se quita en cuanto un turno trabaja con IA
            if sin_ia:
                pausa_sin_ia("juez" if "juez" in str(ultimo.get("error")) else "")
            else:
                from bots.central import obras
                obras.reanudar()
        if sin_ia >= 2:              # dos veces seguidas sin IA: el resto espera a la siguiente ronda (no se gasta en balde)
            hechos = {t["canal"] for t in ronda["turnos"]}
            for k, _ in plan[:maximo]:
                if k not in hechos:
                    ronda["esperan"][k] = "la IA no contesta ahora: lo intenta en la siguiente ronda"
            print("la IA no ha contestado dos turnos seguidos: lo demás, en la siguiente ronda", flush=True)
            break

    from bots.comun import gemini
    gemini.apuntar_portero()
    ronda["terminada"] = privado.ahora()
    resumen_ronda = {k: ronda.get(k) for k in ("empezada", "terminada", "plan", "turnos", "cola_subidos", "sin_sitio")}
    privado.guardar_estado(fichero(a.linea), dict(ronda, linea=a.linea, cuota=subidor.cuota(), cola=len(subidor.en_cola()),
                                                rondas=(rondas + [resumen_ronda])[-30:]))
    guardar("fábrica: fin de la ronda")
    fallos = [t for t in ronda["turnos"] if t["codigo"] != 0]
    if fallos and all(de_fuera(t.get("error")) for t in fallos):
        # sin IA (cupo agotado) o sin el servicio gratis de dibujos: la ronda espera, no es una avería del código
        print("la IA o el servicio de dibujos no contestan ahora: la ronda espera a la siguiente (no es un fallo del "
              "código)", flush=True)
        return 0
    return 1 if ronda["turnos"] and len(fallos) == len(ronda["turnos"]) else 0


if __name__ == "__main__":
    sys.exit(main())
