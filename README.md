# Ciudades

Fábrica de vídeos cortos (YouTube Shorts, TikTok y Reels) que funciona sola en la nube, sin ordenador. Está organizada en cuatro ciudades:

| Ciudad | Qué hace |
|---|---|
| **Central** | Hace los vídeos (guion, voz, dibujos, montaje), los sube a su hora y cuenta las visitas |
| **Juzgado** | Abogados y jueces deciden qué ideas y qué vídeos merecen subirse |
| **Policía** | Vigila a todos los bots y arregla los fallos sola |
| **Influencers** | Estudia los vídeos que se hacen virales y escribe recetas |

**Estado:** en obras. Todavía no hay ningún bot en marcha.

## Herramientas (gratis y probadas)

| Programa | Qué hace |
|---|---|
| `herramientas/voz.py` | Voz en off gratis (edge-tts) con el momento exacto de cada palabra |
| `herramientas/subtitulos.py` | Subtítulos palabra a palabra, estilo karaoke, quemados en el vídeo |
| `herramientas/transcribir.py` | Transcribe el audio de un vídeo (faster-whisper) |
| `herramientas/portada.py` | Portadas y miniaturas con texto gancho |
| `herramientas/fotogramas.py` | Mide un vídeo (ritmo, silencios, pantallas negras, volumen) y saca 7 fotogramas para juzgarlo |
| `herramientas/recortar.py` | Recorta un trozo de un vídeo y lo pasa a vertical 1080x1920 |
| `herramientas/subir.py` | Sube a YouTube en privado y programado, comprobando canal, tope y cuota |
| `herramientas/conectar_canal.py` | Conecta los canales de YouTube sin ordenador (código en google.com/device) y guarda los permisos en los secretos de GitHub |
| `herramientas/avisar.py` | Avisos al móvil gratis (ntfy o Telegram) |
| `herramientas/analizar.py` | Desmonta un vídeo viral para aprender de él |
| `herramientas/palabras_clave.py` | Palabras clave gratis del buscador de YouTube |
| `herramientas/competencia.py` | Qué publican los canales que más crecen en un tema y qué les funciona |
| `herramientas/memoria.py` | La memoria de cada robot: su diario, lo que aprende y lo que está probando |

Cada programa explica cómo se usa con `python herramientas/<programa>.py --help`.

## Privacidad

Este repositorio es público para que GitHub Actions sea gratis. Por eso aquí no hay claves, permisos, ids de canales ni cuentas: todo eso va en los secretos de GitHub (`Settings > Secrets and variables > Actions`). `config/ejemplo-canales.json` enseña la forma de la configuración privada.

Lo que aprenden los robots (su memoria) se guarda en un repositorio aparte y privado, nunca aquí.

Las plantillas para que todo funcione solo están en `docs/plantillas-nube/`. Todavía no están activas: se activarán cuando los bots estén listos.
