# Las dos piezas de la caja del Investigador de webs (.github/workflows/capturas.yml). Se construyen en cada turno
# en la máquina de GitHub y se tiran al acabar.
#  - «filtro»: el filtro de red (squid con filtro.conf). Es la única salida que tiene la caja. Va con squid-openssl
#              para mirar el nombre de dentro de cada túnel (SNI) sin descifrar nada, con un certificado desechable
#              hecho aquí que no sale de la imagen.
#  - «caja»:   el contenedor desechable donde trabaja reverse-api-engineer con un modelo gratis de OpenCode. Todo lo
#              que necesita se instala AQUÍ, antes de capturar (durante la captura no hay PyPI ni npm), con versiones
#              fijas: Python 3.12 de Ubuntu 24.04, Node 22 comprobado con su huella, reverse-api-engineer==0.16.0 y sus
#              dependencias con su huella (rae.lock), opencode-ai@1.18.31, rae-playwright-mcp@0.0.9 y Google Chrome.
#              Sin ninguna llave. El juez (caja.py) arranca como root sin más poderes que cambiar de usuario y parar
#              procesos (turno.py: --cap-drop ALL --cap-add SETUID,SETGID,KILL); rae y todo lo de la IA, como «rae».
#   docker build --target filtro -t caja-filtro:turno herramientas/caja_capturas
#   docker build --target caja   -t caja-captura:turno herramientas/caja_capturas
ARG BASE=ubuntu:24.04@sha256:562111b88caa79c71391c0c4d3c2114a7d5c35915c20561fd893cb1e07929e6b

FROM ${BASE} AS filtro
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends squid-openssl openssl \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /etc/squid/listas \
 && openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj /CN=caja \
      -keyout /etc/squid/caja.pem -out /etc/squid/caja.pem 2>/dev/null \
 && chown proxy:proxy /etc/squid/caja.pem && chmod 0400 /etc/squid/caja.pem
COPY filtro.conf /etc/squid/caja.conf
USER proxy
CMD ["squid", "-N", "-f", "/etc/squid/caja.conf"]

FROM ${BASE} AS caja
ARG NODE_VERSION=22.23.5
ARG NODE_SHA256=cdeb8670a0c81f51b4dc4ac61919f9b1ad917b304bf8221eb939570663d240f8
ENV LANG=C.UTF-8
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
      ca-certificates curl xz-utils python3 python3-venv \
 && curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
 && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
 && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --no-same-owner \
 && rm /tmp/node.tar.xz \
 && curl -fsSLo /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends /tmp/chrome.deb \
 && rm /tmp/chrome.deb && rm -rf /var/lib/apt/lists/* \
 && node --version && google-chrome --version
COPY rae.lock cliente.lock /opt/caja/
RUN python3 -m venv /opt/rae \
 && /opt/rae/bin/pip install -q --no-cache-dir --require-hashes --only-binary :all: -r /opt/caja/rae.lock \
 && python3 -m venv /opt/cliente \
 && /opt/cliente/bin/pip install -q --no-cache-dir --require-hashes --only-binary :all: -r /opt/caja/cliente.lock \
 && /opt/rae/bin/reverse-api-engineer --version
COPY caja.py modelo.py vigilante.py arranque.py /opt/caja/
# Su casa, en 0755 (Ubuntu la hace en 0750): el juez es root SIN poder saltarse permisos (--cap-drop ALL), así que sin
# esto no podría ni entrar en la carpeta de trabajo de rae para lanzarlo ni leer lo que deja (todo acabaría en error)
RUN useradd -m -u 10001 -s /bin/bash rae && chmod 0755 /home/rae
USER rae
WORKDIR /home/rae
# Se bajan ahora OpenCode y el navegador de rae a la caché de npx, para que en la captura arranquen sin red de npm
RUN npm_config_update_notifier=false npx -y opencode-ai@1.18.31 --version \
 && npm_config_update_notifier=false npx -y rae-playwright-mcp@0.0.9 --version \
 && rm -rf /home/rae/.config /home/rae/.local /home/rae/.cache
# El juez: root (sin poderes de más, los quita turno.py), el único que escribe en /salida y en /juez
USER root
WORKDIR /
RUN install -d -m 0711 /juez
ENTRYPOINT ["python3", "-I", "/opt/caja/caja.py"]
