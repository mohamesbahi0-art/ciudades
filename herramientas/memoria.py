"""Memoria de los robots: cada robot tiene su cuaderno, aprende de lo que pasa y mejora.

El cuaderno de cada robot es memoria/<robot>.json dentro del repositorio PRIVADO de memoria (variable MEMORIA_DIR,
por defecto ../ciudades-memoria/memoria). Lleva tres cosas:
  · diario: lo que hizo el robot y qué pasó después (la nota real llega más tarde, por ejemplo a las 48 horas);
  · lecciones: lo que ha aprendido, con sus pruebas y lo seguro que está (las mejores arriba, como mucho 30);
  · experimentos: lo que está probando ahora.

Uso desde los robots (Python):
    import memoria
    m = memoria.Cuaderno("escritor")
    texto = m.para_el_prompt()                      # sus lecciones, listas para leerlas antes de trabajar
    i = m.apuntar("guion", {"canal": "gta", "gancho": "pregunta"})
    m.nota(i, 82, "visitas/hora a las 48 h")        # cuando llega el resultado real
    m.aprender("En gta, los ganchos con pregunta retienen más", pruebas=[i], confianza=0.6)
    m.guardar()
Desde la terminal:
    python memoria.py ver escritor
    python memoria.py aprender escritor "Texto de la lección" --confianza 0.7 --dueno
"""
import argparse
import datetime as dt
import json
import os
import uuid

MAX_LECCIONES = 30
MAX_DIARIO = 500


def ahora():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carpeta():
    return os.environ.get("MEMORIA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                                          "ciudades-memoria", "memoria")


class Cuaderno:
    def __init__(self, robot, dir_memoria=None):
        self.robot = robot
        self.ruta = os.path.join(dir_memoria or carpeta(), f"{robot}.json")
        try:
            with open(self.ruta, encoding="utf-8") as f:
                self.datos = json.load(f)
        except FileNotFoundError:
            self.datos = {"robot": robot, "creado": ahora(), "lecciones": [], "diario": [], "experimentos": []}
        self._al_abrir = self._huella()

    def _huella(self):
        return json.dumps({k: v for k, v in self.datos.items() if k != "actualizado"}, sort_keys=True, ensure_ascii=False)

    # --- lo que hace el robot y lo que pasa después -------------------------------------------
    def apuntar(self, accion, detalle=None):
        """Apunta una acción en el diario y devuelve su id, para ponerle nota cuando llegue el resultado."""
        entrada = {"id": uuid.uuid4().hex[:10], "fecha": ahora(), "accion": accion, "detalle": detalle or {}}
        self.datos["diario"].append(entrada)
        return entrada["id"]

    def nota(self, id_accion, valor, que_mide="", comentario=""):
        """Pone la nota real a una acción (visitas por hora, sentencia, si funcionó o no…)."""
        for e in reversed(self.datos["diario"]):
            if e["id"] == id_accion:
                e["resultado"] = {"valor": valor, "mide": que_mide, "comentario": comentario, "fecha": ahora()}
                return True
        return False

    # --- lo que aprende ----------------------------------------------------------------------
    def aprender(self, texto, pruebas=None, confianza=0.5, del_dueno=False):
        """Añade o refuerza una lección. Las del dueño mandan: entran con confianza máxima y no se olvidan solas."""
        texto = texto.strip()
        for l in self.datos["lecciones"]:
            if l["texto"].lower() == texto.lower():
                l["pruebas"] = sorted(set(l.get("pruebas", [])) | set(pruebas or []))
                l["confianza"] = 1.0 if del_dueno else round(min(0.95, max(l["confianza"], confianza) + 0.05), 2)
                l["del_dueno"] = l.get("del_dueno") or del_dueno
                l["actualizada"] = ahora()
                self._ordenar()
                return l["id"]
        leccion = {"id": uuid.uuid4().hex[:8], "texto": texto, "pruebas": list(pruebas or []),
                   "confianza": 1.0 if del_dueno else round(confianza, 2), "del_dueno": del_dueno,
                   "creada": ahora(), "actualizada": ahora()}
        self.datos["lecciones"].append(leccion)
        self._ordenar()
        return leccion["id"]

    def contradecir(self, id_leccion, motivo=""):
        """Los datos dicen lo contrario: baja la confianza y, si llega a muy poco, la lección se olvida."""
        for l in self.datos["lecciones"]:
            if l["id"] == id_leccion and not l.get("del_dueno"):
                l["confianza"] = round(l["confianza"] - 0.2, 2)
                l.setdefault("en_contra", []).append({"fecha": ahora(), "motivo": motivo})
                l["actualizada"] = ahora()
        self.datos["lecciones"] = [l for l in self.datos["lecciones"] if l["confianza"] > 0.15]
        self._ordenar()

    def probar(self, idea, variantes, medir="visitas por hora a las 48 h"):
        """Abre un experimento: una sola cosa cambia entre las variantes."""
        exp = {"id": uuid.uuid4().hex[:8], "idea": idea, "variantes": variantes, "mide": medir, "abierto": ahora()}
        self.datos["experimentos"].append(exp)
        return exp["id"]

    # --- leer antes de trabajar ------------------------------------------------------------------
    def para_el_prompt(self, cuantas=10):
        """Las mejores lecciones en texto, para leerlas (o meterlas en las instrucciones de la IA) antes de trabajar."""
        mejores = self.datos["lecciones"][:cuantas]
        if not mejores:
            return f"{self.robot}: todavía no ha aprendido nada; trabaja con las reglas de su skill."
        lineas = [f"Lo que ha aprendido {self.robot} (de lo más seguro a lo menos):"]
        for l in mejores:
            marca = " (lo dijo el dueño)" if l.get("del_dueno") else ""
            lineas.append(f"- {l['texto']}{marca} [seguridad {int(l['confianza'] * 100)} %]")
        return "\n".join(lineas)

    # --- guardar ---------------------------------------------------------------------------------
    def _ordenar(self):
        lecciones = sorted(self.datos["lecciones"], key=lambda l: (not l.get("del_dueno"), -l["confianza"], l["creada"]))
        del_dueno = [l for l in lecciones if l.get("del_dueno")]
        resto = [l for l in lecciones if not l.get("del_dueno")][:max(0, MAX_LECCIONES - len(del_dueno))]
        self.datos["lecciones"] = del_dueno + resto

    def guardar(self):
        """Guarda el cuaderno, solo si ha cambiado algo (así dos turnos a la vez no se pisan sin necesidad)."""
        self.datos["diario"] = self.datos["diario"][-MAX_DIARIO:]
        if self._huella() == self._al_abrir and os.path.exists(self.ruta):
            return
        self.datos["actualizado"] = ahora()
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        with open(self.ruta + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.datos, f, ensure_ascii=False, indent=1)
        os.replace(self.ruta + ".tmp", self.ruta)
        self._al_abrir = self._huella()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="orden", required=True)
    v = sub.add_parser("ver")
    v.add_argument("robot")
    a = sub.add_parser("aprender")
    a.add_argument("robot")
    a.add_argument("texto")
    a.add_argument("--confianza", type=float, default=0.5)
    a.add_argument("--dueno", action="store_true", help="lo ha dicho el dueño: manda sobre lo demás")
    o = p.parse_args()
    c = Cuaderno(o.robot)
    if o.orden == "aprender":
        c.aprender(o.texto, confianza=o.confianza, del_dueno=o.dueno)
        c.guardar()
    print(c.para_el_prompt(30))
    print(f"(diario: {len(c.datos['diario'])} acciones · experimentos abiertos: {len(c.datos['experimentos'])})")


if __name__ == "__main__":
    main()
