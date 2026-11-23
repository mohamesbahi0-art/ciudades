# Ciudades: instrucciones para Claude

Es la fábrica de vídeos del dueño, rehecha en la nube tras perder su portátil. Las skills de su cuenta de Claude lo explican todo. Empieza por la skill `ciudades`, que tiene los detalles privados (canales, cuentas, la app y el protocolo de avisos), y sigue con las de cada ciudad (`ciudad-central`, `juzgado`, `policia`, `influencers` y `para-subir`) y las herramientas (`voz-y-subtitulos`, `portadas`, `predictor-viral`, `recortador-clips`, `subidor-youtube`, `analista-virales`, `nube-automatica`, `avisos-movil` y `guiones-virales`).

## Este repositorio es PÚBLICO

Lo es para que GitHub Actions sea gratis. Nunca subas:

- claves, `client_secret`, contraseñas ni permisos de YouTube (tokens), ni siquiera cifrados. Los permisos de los canales viven solo en los secretos de GitHub (`YT_REFRESH_<CANAL>` y `YT_ID_<CANAL>`); nunca los imprimas;
- ids de canales, nombres de cuentas de Instagram o TikTok, correos o rutas del ordenador del dueño;
- la lista de creadores que han dado permiso, ni nada copiado de la carpeta rescatada del portátil sin limpiarlo.

Las claves y los permisos van en los secretos de GitHub. Los datos privados (la lista oficial completa, la configuración de canales y barrios en `config/canales.json`, los cuadernos de memoria, el estado y el registro de subidas) van en el repositorio **privado** `ciudades-memoria`. Los turnos lo leen con la llave `GH_SECRETOS`. Antes de cada commit, busca que no se cuele nada de esto.

## Cómo está ordenado

- `herramientas/`: programas genéricos y probados (voz, subtítulos, portadas, medidas, recortes, subida, avisos y análisis).
- `bots/`: el código de cada ciudad. `bots/central/fabrica.py` es la ronda de la fábrica: vacía la cola, decide qué canales y barrios necesitan vídeo (huecos.py) y hace un turno por cada uno (turno.py: reportero → escritor → locutor → dibujante → montador → juez de guardia → subidor o bandeja «Para subir»). `bots/influencers/analista.py` es la Analista de cuentas.
- `bots/comun/ia.py` decide quién piensa: las ideas y los guiones, Claude (`bots/comun/claude.py`, con los 100 $ al mes de API del plan del dueño, secreto `ANTHROPIC_API_KEY`, gastando cada día solo su parte); el juez, Gemini gratis con Claude de reserva; lo demás, Gemini. Sin llave o sin presupuesto, todo sigue con Gemini. Los topes están en `config/fabrica.json` → `claude` (repositorio privado) y el gasto en `estado/claude.json`; las cifras nunca van a los registros públicos.
- `bots/central/clips.py`: el Montador de clips. El Buscador de clips elige trozos de vídeos de GTA con licencia libre (CC BY): solo los de 90 o más y sin nada del creador. El dueño los graba con el móvil y los sube en la app, y la ronda del Comisario los deja en una rama temporal del repositorio privado (`buzon/<codigo>`). En el turno de su canal (que va el primero), el Portero de clips deja solo el juego: recorta, quita la voz del creador o descarta el clip. Después va como todos (narración, Jurado, Juzgado, Coliseo y subida). Del creador solo va su nombre en la descripción. La fábrica borra la rama al terminar.
- `bots/central/videoteca.py`: la Videoteca de juego. Al empezar cada ronda, el Archivero pasa cada clip grabado por el Portero y guarda la versión limpia en la estantería «videoteca», con su juego (GTA 5 o GTA 6), sus etiquetas y lo que se ve. Después borra su rama. Los canales con `videoteca: true` (gta, curios y versus) hacen sus vídeos con esas tomas en vez de dibujos cuando hay bastantes: 6 de su juego sacadas de al menos 2 vídeos, o 2 cosas con toma de GTA 5 y de GTA 6 para el versus. Cada escena enseña lo que dice la voz y los planos duran de 2 a 3 s. El versus va en pantalla partida, con GTA 5 arriba y GTA 6 abajo, por rondas y con ganador. Las tomas las trae solo el Recolector (cada día); las que el dueño grabe de la lista del Buscador (los lunes) son un extra.
- `bots/central/recolector.py`: el Recolector de clips (`recolector.yml`, cada día a las 9:11 UTC). Trae solo, sin que el dueño haga nada, tomas y momentos de GTA 5 y GTA 6 de Internet Archive, que deja bajar sus vídeos a los robots: no se salta nada. Solo valen las licencias CC BY y CC0; fuera NC, ND, SA, la «marca de dominio público», lo filtrado, los tráileres y las charlas. La IA mira muestras de cada vídeo sin bajarlo entero. Cada trozo se corta, se limpia como en el Portero y va a la Videoteca con su crédito (autor, enlace y licencia). Los momentos virales quedan listos para su Short. Se para con 600 tomas. La lista «Para grabar» del Buscador de YouTube es opcional (los lunes).
- `bots/juzgado/ventanilla.py`: la Ventanilla del Juzgado («Juzga mi vídeo», `ventanilla.yml`). El dueño sube su propio vídeo en la app; la ronda de Claude lo deja en una rama temporal del repositorio privado (`juicio/<codigo>`, con `peticion.json`) y escribe `peticiones/juicio.json` (solo el código). Pasa por el Jurado popular, el Juzgado completo y, si aprueba, por el Coliseo; si no, vuelve con los arreglos en sencillo. El resultado queda en `estado/propios/<codigo>.json`, avisa al móvil y borra la rama.
- `bots/central/constructor.py`: el Constructor de canales (`constructor.yml`). Cuando el dueño pida «crea otro canal», deja la petición en el repositorio privado (`config/nuevos/<alias>.json`: red, clave, nombre, tema, idioma, parecido_a y, si es de TikTok/Instagram, cuenta) y escribe `peticiones/canal_nuevo.json` (`{"alias": "nuevo-1"}`, nunca el nombre). Hace la ficha, la entrada en `config/canales.json`, la foto y el banner (estantería «canales») y, si el canal de YouTube ya está conectado, le pone descripción, etiquetas y banner. Una cuenta nueva de TikTok/Instagram queda en pausa hasta que el dueño apruebe su primera muestra. Al conectar un canal nuevo, añade sus `YT_REFRESH_`/`YT_ID_` a `fabrica.yml`, `revisar-canales.yml` y `constructor.yml`.
- `bots/central/directos.py`: el Presentador de directos (`directos.yml`, los lunes a las 15:23 UTC, o con `peticiones/directo.json`). El directo lo hace el dueño; el bot le deja el de la semana de cada cuenta encendida (guion por bloques, preguntas para el chat, encuesta, reto y lo que no hay que hacer) en `estado/directos/<alias>.json`.
- `bots/estudio/bolas.py` + `bolas.html`: los vídeos de bolas-país del canal de mapas (formato «bolas»). El Archivero de mapas (`archivero_mapas.py`) elige país y parte siguiendo los títulos («… (Parte N)», que siempre empiezan por el país): termina las series a medias y empieza países nuevos sin repetir (fuera los países en guerra). El Cartógrafo (`cartografo.py`) tiene el mapa (`datos/mundo.json`, de Natural Earth, dominio público; se rehace con `cartografo.py construir countries-110m.json`) y da a cada escena su encuadre y a cada bola su sitio. Banderas: `banderas/` (flag-icons, MIT).
- `bots/coliseo/coliseo.py`: el Coliseo (sexta ciudad). Cada vídeo que el Juzgado aprueba con 90 o más entra en un torneo de 8 gladiadores (cartas distintas) que pelean por su salida (título, texto y hashtags), con combates por parejas y un juez ciego; la campeona es la que se publica. Tope diario en `config/fabrica.json` → `coliseo`. Si algo falla, el vídeo sale con su salida de siempre.
- `ciudades.json`: la lista pública de ciudades y bots, sin datos de canales.
- `.github/workflows/`: los turnos que corren solos en GitHub, aunque Claude y el ordenador estén apagados:
  - `fabrica.yml`: cada 2 horas (minuto 17); también con `peticiones/fabrica.json` (`{"solo": "gta", "maximo": 1}`).
  - `revisar-canales.yml`: cada 3 horas (minuto 37): Jefes de canal y Analista.
  - `derechos.yml`: cada día (10:29 UTC): Derechos Sociales (Doctora, Equipo de mejora, Defensora, Guía, Psicóloga y Jefe) cuidan de los robots; `estudio.yml` (cada día) lleva también al Entrenador.
  - `ojeador.yml`: cada 3 horas (minuto 7): el Ojeador de redes mira TikTok e Instagram sin cuenta (si una red dice que no, la deja en paz unas horas; nunca se salta un bloqueo).
  - `conectar-canales.yml`, `prueba-central.yml` y `probar-descarga.yml`: solo con su fichero de `peticiones/`.
- `docs/plantillas-nube/`: plantillas de turnos que todavía no están activos.
- El estado que dejan los bots va al repositorio **privado** (`estado/`, `parasubir/`, `cola/`, `registro/`), y una ronda de Claude programada lo copia a la app.

**Los registros de GitHub Actions de este repositorio son públicos.** Los bots solo escriben en ellos la clave del canal y el paso; los barrios (cuentas de TikTok e Instagram) salen como `barrio-1`, `barrio-2`… (`privado.alias`, `privado.limpiar`). En `peticiones/` usa también esos alias, nunca el nombre de la cuenta. Los vídeos se guardan como archivos de «releases» del repositorio privado (`bots/comun/almacen.py`), nunca en el historial. Las sesiones de Claude no pueden escribir en las «releases»: por eso los clips del dueño viajan en una rama temporal `buzon/<codigo>` (un commit suelto, fuera de `main`) que borra la fábrica.

## Memoria de los robots

Cada robot tiene su cuaderno (`memoria/<robot>.json`) en el repositorio **privado** `ciudades-memoria`, nunca en este. Se maneja con `herramientas/memoria.py` (variable `MEMORIA_DIR`) y lo explica la skill `memoria`. Antes de trabajar, el robot lee sus lecciones; después apunta lo que hizo y, cuando llega el resultado real, le pone la nota. Lo que dice el dueño entra como lección suya y manda.

## Conectar o reconectar canales de YouTube

1. Escribe `peticiones/conectar.json` con `{"canales": {"<clave>": "<huella>"}}`. La huella son los 16 primeros caracteres del sha256 del id del canal, con los ids de la lista privada (skill `ciudades`). Añade `"rehacer": true` para renovar permisos que ya existen.
2. Haz commit y push. El turno «Conectar canales» deja en `estado/conexion.json` un código.
3. Dale el código al dueño: lo escribe en google.com/device desde el móvil, elige ese canal y pulsa «Permitir». Si sale «Google no ha verificado esta aplicación», entra por «Configuración avanzada».
4. Vigila `estado/conexion.json` (git pull): `conectado`, `rechazado`, `otro_canal`, `caducado`, `error` o `terminado`. Si elige otro canal de la lista, se guarda en el suyo y se vuelve a pedir el que faltaba.

El permiso de cada canal se guarda directamente como secreto de GitHub (`YT_REFRESH_<CANAL>` y `YT_ID_<CANAL>`). Hacen falta los secretos `YT_CLIENT_ID` y `YT_CLIENT_SECRET` (cliente de Google del tipo «TVs y dispositivos de entrada limitada») y `GH_SECRETOS` (llave de GitHub con permiso solo para escribir secretos de este repositorio).

## Con el dueño

Háblale en español de España, sencillo y sin tecnicismos. No entiende la parte técnica y quiere que todo se arregle solo: arréglalo y cuéntaselo después. Todo gratis, salvo que él pida otra cosa. Cada cambio que afecte a la app se avisa al chat «app ciudad», como dice la skill `ciudades`.
