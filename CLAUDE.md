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
- `ciudades.json`: la lista pública de ciudades y bots, sin datos de canales.
- `.github/workflows/`: los turnos que corren solos en GitHub, aunque Claude y el ordenador estén apagados:
  - `fabrica.yml`: cada 2 horas (minuto 17); también con `peticiones/fabrica.json` (`{"solo": "gta", "maximo": 1}`).
  - `revisar-canales.yml`: cada 3 horas (minuto 37): Jefes de canal y Analista.
  - `conectar-canales.yml`, `prueba-central.yml` y `probar-descarga.yml`: solo con su fichero de `peticiones/`.
- `docs/plantillas-nube/`: plantillas de turnos que todavía no están activos.
- El estado que dejan los bots va al repositorio **privado** (`estado/`, `parasubir/`, `cola/`, `registro/`), y una ronda de Claude programada lo copia a la app.

**Los registros de GitHub Actions de este repositorio son públicos.** Los bots solo escriben en ellos la clave del canal y el paso; los barrios (cuentas de TikTok e Instagram) salen como `barrio-1`, `barrio-2`… (`privado.alias`, `privado.limpiar`). En `peticiones/` usa también esos alias, nunca el nombre de la cuenta. Los vídeos se guardan como archivos de «releases» del repositorio privado (`bots/comun/almacen.py`), nunca en el historial.

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
