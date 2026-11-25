"""El Juzgado Mayor: juicio completo a cada vídeo antes de subirlo, como el tribunal de la fábrica antigua pero con
menos llamadas a la IA (2 en vez de 10), para que quepa en el cupo gratis.

1. Detectives (Paco Lupa para la defensa, Elena Rastro para la fiscalía): sacan pruebas de los datos reales, sin IA:
   visitas normales del canal, los vídeos que mejor y peor fueron y lo que pasó con títulos parecidos.
2. Abogados: la letrada Sofía Vargas defiende que el vídeo va a funcionar y el fiscal Héctor Duro, que no (1 llamada,
   mirando los fotogramas).
3. Salas: la jueza Carmen Gancho (los 2 primeros segundos), el juez Ramón Reloj (que se vea entero) y la jueza Lola Calle
   (si a la gente le importa) votan sube o no, con nota de 0 a 100 (1 llamada).
4. (El Jurado popular, jurado.py, ya votó el guion antes de grabarlo: su veredicto se guarda con el juicio.)
5. Juez Mayor: el juez que más acierta en la Liga (al principio, Ramón Reloj) dicta la sentencia: manda la mayoría y, si
   hay empate, su voto. Fallo grave (pantalla negra, sin voz…) = no sube.

Si la IA no contesta, juicio rápido del Juez de guardia; si tampoco, el vídeo pasa sin juicio (ningún canal se queda sin
vídeos). Cada juicio queda en estado/juzgado/juicios/ para la app.
"""
import datetime as dt
import json
import os
import statistics
import subprocess
import sys

from bots.comun import gemini, ia, privado
from bots.juzgado import juez_guardia, publico

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JUECES = {
    "gancho": {"nombre": "Jueza Carmen Gancho", "sala": "Sala del Gancho",
               "especialidad": "los 2 primeros segundos: si la imagen, el texto grande y lo primero que se oye hacen parar el dedo"},
    "reloj": {"nombre": "Juez Ramón Reloj", "sala": "Sala del Reloj",
              "especialidad": "la retención: si se ve entero, si hay partes muertas o relleno y si apetece verlo otra vez"},
    "calle": {"nombre": "Jueza Lola Calle", "sala": "Sala de la Calle",
              "especialidad": "el público: si a la gente le importa este tema ahora, si el título da ganas de verlo y si provoca comentarios"},
}
JEFE_INICIAL = "reloj"
NOTA_MINIMA = 90          # solo si falla la escalera del dueño (privado.nota_minima): 80 ahora y sube por semanas

ABOGADOS = """Eres el Juzgado de {donde} «{nombre}». Hoy se juzga si este vídeo merece subirse. El vídeo está en {idioma}.
Título: {titulo}
Texto del principio: {gancho}
Narración: {narracion}
Medidas: {medidas}
Te paso 7 fotogramas en orden (del principio al final) y la voz entera (escúchala: ritmo, claridad, emoción).

Pruebas del detective Paco Lupa (para la defensa) y de la detective Elena Rastro (para la fiscalía), con datos reales:
{pruebas}

Lo que ha aprendido el Juzgado (lo del dueño manda):
{lecciones}

Escribe los dos alegatos, cortos y con argumentos concretos (usa las pruebas, no te inventes cifras):
- la letrada Sofía Vargas defiende que el vídeo va a funcionar;
- el fiscal Héctor Duro dice que no y señala sus fallos.
Devuelve SOLO un JSON: {{"defensa": "3-4 frases", "fiscalia": "3-4 frases", "fallos_graves": ["solo si hay pantalla negra, vídeo sin voz, imágenes rotas o con letras deformadas, título sin relación o algo que rompa las normas de YouTube o TikTok (un tema duro u oscuro no es un fallo)"]}}"""

SALAS = """Eres el Juzgado de {donde} «{nombre}». Tres jueces deciden si este vídeo se sube. Fotogramas y voz adjuntos.
Título: {titulo}
Texto del principio: {gancho}
Medidas: {medidas}

Alegato de la defensa (Sofía Vargas): {defensa}
Alegato de la fiscalía (Héctor Duro): {fiscalia}

Los jueces, cada uno mirando SOLO su especialidad:
{jueces}
{exigencia}
Los dibujos hechos con IA son el estilo del canal: no es un fallo. Un tema duro, oscuro o incómodo tampoco: el dueño
quiere vídeos sin miedo; solo cuenta que enganche.
Devuelve SOLO un JSON: {{"votos": [{{"juez": "gancho|reloj|calle", "voto": "sube" o "no", "nota": 0-100, "razon": "una frase"}}],
"consejo": "una frase concreta para mejorar el próximo vídeo"}}"""


def _pruebas(clave, canal):
    """Lo que encuentran los detectives en los datos reales (sin IA)."""
    rev = privado.leer(os.path.join("estado", "canales", f"{clave}.json"), {}) or {}
    recientes = rev.get("recientes", [])
    medidas = [m for m in (privado.leer(os.path.join("estado", "juzgado", "mediciones.json"), {}) or {}).values()
               if m.get("canal") == clave]
    lineas = []
    if recientes:
        visitas = [v["visitas"] for v in recientes]
        lineas.append(f"- Normal del canal: mediana de {int(statistics.median(visitas))} visitas en sus últimos "
                      f"{len(visitas)} vídeos; {rev.get('suscriptores', '?')} suscriptores.")
        mejores = sorted(recientes, key=lambda v: v["visitas"], reverse=True)
        lineas.append("- Los que mejor fueron: " + "; ".join(f"«{v['titulo']}» ({v['visitas']})" for v in mejores[:3]))
        lineas.append("- Los que peor fueron: " + "; ".join(f"«{v['titulo']}» ({v['visitas']})" for v in mejores[-3:]))
    else:
        lineas.append("- El canal todavía no tiene vídeos públicos con visitas que comparar.")
    if medidas:
        lineas.append(f"- Vídeos nuestros ya medidos a las 48 h: {len(medidas)}; mediana "
                      f"{int(statistics.median(m['visitas'] for m in medidas))} visitas.")
    return "\n".join(lineas)


def _jefe():
    liga = (privado.leer(os.path.join("estado", "juzgado", "liga.json"), {}) or {}).get("jueces", {})
    candidatos = [(d.get("aciertos") or 0, k) for k, d in liga.items() if k in JUECES and (d.get("comparaciones") or 0) >= 10]
    return max(candidatos)[1] if candidatos else JEFE_INICIAL


def minima(canal):
    """La nota mínima para publicar: la del perfil si la tiene; si no, la de la escalera del dueño para hoy
    (privado.nota_minima: 80 al principio, y sube con las semanas)."""
    try:
        if canal and canal.get("nota_minima") is not None:
            return int(canal["nota_minima"])
    except (TypeError, ValueError):
        pass
    return privado.nota_minima()


def exigencia(canal):
    m = minima(canal)
    if m < 80:
        return ""
    return (f"OJO: esta cuenta solo publica vídeos de {m} o más sobre 100. Sé muy exigente: {m} es un vídeo excelente, que "
            "la gente vería entero y compartiría. Si es «correcto» o «está bien», no llega: ponle menos de 80 y di qué falta.")


def _sentenciar(sala, alegatos, fallos, canal, guion, medidas, gente):
    """De los votos de la sala a la sentencia. None si los jueces no han contestado bien."""
    votos = []
    for voto in sala.get("votos", []) or []:
        k = voto.get("juez") if isinstance(voto, dict) else None
        if k in JUECES:
            try:
                nota = max(0, min(100, int(voto.get("nota", 0))))
            except (TypeError, ValueError):
                continue
            votos.append({"juez": JUECES[k]["nombre"], "clave": k, "voto": "sube" if voto.get("voto") == "sube" else "no",
                          "nota": nota, "razon": voto.get("razon", "")})
    if not votos:
        return None
    jefe = _jefe()
    a_favor = sum(1 for v in votos if v["voto"] == "sube")
    voto_jefe = next((v["voto"] for v in votos if v["clave"] == jefe), "sube")
    total = round(statistics.mean(v["nota"] for v in votos))
    sube = (a_favor * 2 > len(votos)) or (a_favor * 2 == len(votos) and voto_jefe == "sube")
    if fallos or total < minima(canal):
        sube = False
    # El Jurado popular ya votó el guion antes de grabarlo (turno.py): su veredicto va con el juicio para la app y la Liga
    return {"veredicto": "aprobado" if sube else "suspendido", "total": total, "fallos_graves": fallos,
            "consejo": sala.get("consejo", "") or "", "jurado": guion.get("jurado"),
            "defensa": alegatos.get("defensa", ""), "fiscalia": alegatos.get("fiscalia", ""), "votos": votos,
            "juez_mayor": JUECES[jefe]["nombre"], "medidas": medidas, "tribunal": "juicio completo",
            "cerebro": ia.quien().get("motor", "gemini"), "publico": gente}


def _apunta_suplente(clave, guion, resultado):
    """El Juez suplente apunta su juicio en su cuaderno (para compararlo después con el del juez de primera)."""
    try:
        c = privado.cuaderno("juez_suplente")
        i = c.apuntar("juicio", {"canal": clave, "titulo": str(guion.get("titulo", ""))[:120],
                                 "veredicto": resultado.get("veredicto"), "total": resultado.get("total"),
                                 "cerebro": resultado.get("cerebro")})
        c.guardar()
        return i
    except Exception:
        return None


def nota_suplente(id_apunte, de_primera):
    """Cuando un juez de primera juzga lo mismo que juzgó el suplente, el suplente se apunta la nota buena: aprende
    si va largo o corto."""
    if not id_apunte:
        return
    try:
        c = privado.cuaderno("juez_suplente")
        c.nota(id_apunte, de_primera.get("total"), "nota del juez de primera sobre el mismo vídeo",
               str(de_primera.get("consejo") or "")[:300])
        c.guardar()
    except Exception:
        pass


def _espera(resultado, motivo):
    """Un aprobado que todavía no vale: lo ha dado un juez suplente y falta que lo confirme uno de primera."""
    resultado.update(veredicto="sin_juicio", preaprobado=True, nota_suplente=resultado.get("total"),
                     suplente=resultado.get("cerebro"), motivo=motivo)
    return resultado


def juzgar(video, guion, canal, lecciones, carpeta, audio=None, prueba=False, confirmar=False, publico_previo=None):
    """El juicio completo. Los jueces suplentes (la IA gratis de reserva) pueden suspender y decir qué arreglar, pero un
    aprobado suyo no vale hasta que lo confirme un juez de primera: si ahora no hay ninguno, devuelve «sin_juicio» con
    preaprobado=True y el vídeo espera en la Sala de espera. confirmar=True: es ese segundo juicio, solo con jueces de
    primera (si siguen sin estar, vuelve a devolver «sin_juicio»)."""
    clave = canal["clave"]
    subprocess.run([sys.executable, os.path.join(RAIZ, "herramientas", "fotogramas.py"), video, "--salida", carpeta],
                   check=True, capture_output=True)
    with open(os.path.join(carpeta, "datos.json"), encoding="utf-8") as f:
        datos = json.load(f)
    medidas = juez_guardia.medidas_para(datos, canal, guion)
    fallos = []
    negras = [n for n in datos.get("pantallas_negras") or [] if n.get("hasta", 0) - n.get("desde", 0) >= 0.8]
    if negras:                       # un fundido corto no cuenta: solo pantallas negras de casi un segundo o más
        fallos.append("pantalla negra")
    if datos.get("sin_audio"):
        fallos.append("sin voz")
    imagenes = [os.path.join(carpeta, f["archivo"]) for f in datos["fotogramas"]]
    imagenes = [r for r in imagenes if os.path.exists(r)]      # un fotograma que no se pudo sacar no tumba el juicio
    comun = {"donde": "un canal de YouTube Shorts" if canal.get("destino", "youtube") == "youtube"
             else "una cuenta de Instagram y TikTok", "nombre": canal["nombre"],
             "idioma": {"es": "español", "nl": "neerlandés"}.get(canal.get("idioma", "es")[:2], "español"),
             "titulo": guion["titulo"], "gancho": guion.get("texto_pantalla", ""),
             "medidas": json.dumps(medidas, ensure_ascii=False),
             "exigencia": exigencia(canal) + juez_guardia.nota_formato(canal)}
    try:                  # el Público mira el vídeo montado antes que nadie: su retención es una prueba más
        gente = publico_previo or publico.mirar(guion, canal, imagenes, datos.get("duracion"), prueba=prueba)
    except Exception:
        gente = None
    del_publico = ("\n- " + publico.en_palabras(gente) + " (es un público simulado: tenlo en cuenta como una prueba "
                   "fuerte de si engancha, sobre todo dónde y por qué se va la gente)") if gente else ""
    comun["exigencia"] += del_publico
    jueces_txt = "\n".join(f"- {k}: {j['nombre']} ({j['sala']}): {j['especialidad']}" for k, j in JUECES.items())

    def la_sala(alegatos, solo_primera):
        return ia.preguntar(SALAS.format(defensa=alegatos.get("defensa", ""), fiscalia=alegatos.get("fiscalia", ""),
                                         jueces=jueces_txt, **comun), papel="juez", imagenes=imagenes, solo_bueno=True,
                            temperatura=0.3, audio=audio, solo_primera=solo_primera)
    try:
        alegatos = ia.preguntar(ABOGADOS.format(narracion=guion["narracion"], pruebas=_pruebas(clave, canal) + del_publico,
                                                lecciones=lecciones, **comun), papel="juez", imagenes=imagenes,
                                solo_bueno=True, temperatura=0.5, audio=audio, solo_primera=confirmar)
        sala = la_sala(alegatos, confirmar)
        if not isinstance(alegatos, dict) or not isinstance(sala, dict):
            raise gemini.SinIA("la IA no contestó con la forma pedida")
        resultado = _sentenciar(sala, alegatos, fallos + [str(x) for x in alegatos.get("fallos_graves", []) or [] if x],
                                canal, guion, medidas, gente)
    except Exception as e:                 # sin IA o con respuesta rara
        if confirmar:                      # la confirmación solo vale de un juez de primera: si no está, sigue esperando
            return {"veredicto": "sin_juicio", "preaprobado": True, "medidas": medidas, "publico": gente,
                    "motivo": f"no hay juez de primera para confirmar ({str(e)[:120]})"}
        resultado = None
    if resultado is None:                  # juicio rápido del Juez de guardia
        if confirmar:
            return {"veredicto": "sin_juicio", "preaprobado": True, "medidas": medidas, "publico": gente,
                    "motivo": "los jueces de primera no contestaron bien"}
        v = juez_guardia.juzgar(video, guion, canal, lecciones, carpeta + "-guardia")
        v["tribunal"] = "juicio rápido (la IA no daba para el juicio completo)"
        if v.get("veredicto") == "aprobado" and ia.es_suplente(v.get("cerebro")) and not prueba:
            return _espera(v, "lo ha dado por bueno un juez suplente en un juicio rápido: falta el juez de primera")
        return v
    id_suplente = _apunta_suplente(clave, guion, resultado) \
        if ia.es_suplente(resultado.get("cerebro")) and not prueba and not confirmar else None
    if resultado["veredicto"] == "aprobado" and ia.es_suplente(resultado.get("cerebro")) and not prueba:
        # lo aprueba un suplente: que lo confirme ahora mismo un juez de primera (con los mismos alegatos)
        suplente, nota_del_suplente = resultado.get("cerebro"), resultado.get("total")
        try:
            segunda = la_sala(alegatos, True)
            confirmado = _sentenciar(segunda, alegatos, resultado["fallos_graves"], canal, guion, medidas, gente) \
                if isinstance(segunda, dict) else None
        except Exception:
            confirmado = None
        if confirmado is None:
            resultado = _espera(resultado, "lo ha dado por bueno un juez suplente: falta que lo confirme uno de primera")
            resultado["id_suplente"] = id_suplente
        else:
            resultado = dict(confirmado, instruccion={"cerebro": suplente, "total": nota_del_suplente})
            nota_suplente(id_suplente, confirmado)
    elif ia.es_suplente(resultado.get("cerebro")):
        resultado["suplente"] = resultado.get("cerebro")
    total, sube = resultado.get("total"), resultado["veredicto"] == "aprobado"
    try:                                                  # en directo al móvil del dueño
        from bots.central import cartero
        if resultado.get("preaprobado"):
            cartero.directo(f"⚖️ Juzgado: {resultado.get('nota_suplente')}/100 del juez suplente · ESPERA al juez de primera",
                            f"«{guion['titulo']}»\nEl juez de reserva lo da por bueno, pero nada sale sin que lo confirme "
                            "un juez de primera. Se queda en la Sala de espera.", etiqueta="scales")
        else:
            cartero.directo(f"⚖️ Juzgado: {total}/100 · {'APROBADO' if sube else 'NO PASA'} (hace falta {minima(canal)})",
                            f"«{guion['titulo']}»\n🟢 Defensa: {resultado.get('defensa', '')[:300]}\n🔴 Fiscalía: "
                            f"{resultado.get('fiscalia', '')[:300]}\n" + "\n".join(
                                f"{'✅' if x['voto'] == 'sube' else '❌'} {x['juez']} ({x['nota']}): {x['razon'][:200]}"
                                for x in resultado["votos"]) +
                            (f"\n💡 {resultado['consejo'][:300]}" if resultado.get("consejo") else "")
                            + (f"\n⛔ Fallos graves: {', '.join(resultado['fallos_graves'])}"
                               if resultado.get("fallos_graves") else ""), etiqueta="scales")
    except Exception:
        pass
    with open(os.path.join(carpeta, "veredicto.json"), "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=1)
    return resultado


def guardar_juicio(clave, guion, v, prueba=False):
    """Deja el juicio para la app (juicios/{id}) y lo apunta en los cuadernos del Juzgado."""
    if v.get("tribunal") != "juicio completo":
        return None
    ahora = dt.datetime.now(dt.timezone.utc)
    id_juicio = f"{ahora.strftime('%Y%m%d-%H%M%S')}-{clave}".replace(".", "-")
    a_favor = sum(1 for x in v["votos"] if x["voto"] == "sube")
    j = v.get("jurado") or {}
    del_jurado = (f" Jurado popular: {j.get('inocente')} inocente y {j.get('culpable')} culpable."
                  if j.get("votos") else "")
    resumen = (f"{a_favor} de {len(v['votos'])} jueces votaron que sube. Nota media {v['total']}/100.{del_jurado} "
               f"Sentencia del {v['juez_mayor']}: {'se sube' if v['veredicto'] == 'aprobado' else 'no se sube'}.")
    privado.guardar_estado(f"juzgado/juicios/{id_juicio}.json", {
        "canal": clave, "tipo": "video", "titulo": guion["titulo"], "defensa": v["defensa"], "fiscalia": v["fiscalia"],
        "votos": [{"juez": x["juez"], "voto": x["voto"], "nota": x["nota"], "razon": x["razon"]} for x in v["votos"]],
        "sentencia": "sube" if v["veredicto"] == "aprobado" else "no_sube", "juez": v["juez_mayor"],
        "fecha": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"), "resumen": resumen, "consejo": v.get("consejo"),
        "fallos_graves": v.get("fallos_graves"), "prueba": prueba, "intento": v.get("intento", 1),
        "version": v.get("version", 1), "arreglo_de": guion.get("arreglo_de"),
        "nota": v["total"], "minimo": v.get("minimo") or privado.nota_minima(), "cerebro": v.get("cerebro"), "guionista": guion.get("cerebro"),
        "instruccion": v.get("instruccion"),      # si antes lo dio por bueno un juez suplente: quién y con qué nota
        "jurado": v.get("jurado"), "publico": v.get("publico"),
        "publico_resumen": publico.en_palabras(v.get("publico")) or None})
    for robot, que in (("detectives", "pruebas"), ("abogados", "alegatos"), ("jueces_sala", "votos"),
                       ("juez_mayor", "sentencia")):
        c = privado.cuaderno(robot)
        c.apuntar(que, {"canal": clave, "juicio": id_juicio, "sentencia": v["veredicto"], "total": v["total"],
                        "votos": {x["clave"]: x["nota"] for x in v["votos"]}})
        c.guardar()
    return id_juicio
