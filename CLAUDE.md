# Ciudades: instrucciones para Claude

Es la fábrica de vídeos del dueño, rehecha en la nube tras perder su portátil. Las skills de su cuenta de Claude lo explican todo. Empieza por la skill `ciudades`, que tiene los detalles privados (canales, cuentas, la app y el protocolo de avisos), y sigue con las de cada ciudad (`ciudad-central`, `juzgado`, `policia`, `influencers` y `para-subir`) y las herramientas (`voz-y-subtitulos`, `portadas`, `predictor-viral`, `recortador-clips`, `subidor-youtube`, `analista-virales`, `nube-automatica`, `avisos-movil` y `guiones-virales`).

## Este repositorio es PÚBLICO

Lo es para que GitHub Actions sea gratis. Nunca subas:

- claves, permisos de YouTube (tokens), `client_secret` ni contraseñas;
- ids de canales, nombres de cuentas de Instagram o TikTok, correos o rutas del ordenador del dueño;
- la lista de creadores que han dado permiso, ni nada copiado de la carpeta rescatada del portátil sin limpiarlo.

Todo eso va en los secretos de GitHub. La configuración de canales y barrios es el secreto `CONFIG_CANALES` (un JSON con la forma de `config/ejemplo-canales.json`). Antes de cada commit, busca que no se cuele nada de esto.

## Cómo está ordenado

- `herramientas/`: programas genéricos y probados (voz, subtítulos, portadas, medidas, recortes, subida, avisos y análisis).
- `ciudades.json`: la lista pública de ciudades y bots, sin datos de canales.
- `docs/plantillas-nube/`: los turnos de GitHub Actions. Todavía no están activos; pásalos a `.github/workflows/` solo cuando los bots existan y el dueño esté de acuerdo.
- `bots/` (pendiente): el código de cada ciudad.
- `estado/` (pendiente): lo que dejan los bots y una ronda de Claude copia a la app.

## Con el dueño

Háblale en español de España, sencillo y sin tecnicismos. No entiende la parte técnica y quiere que todo se arregle solo: arréglalo y cuéntaselo después. Todo gratis, salvo que él pida otra cosa. Cada cambio que afecte a la app se avisa al chat «app ciudad», como dice la skill `ciudades`.
