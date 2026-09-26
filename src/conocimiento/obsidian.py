"""Persistencia final: red de notas Markdown para Obsidian.

No se usa SQLite, MongoDB ni Neo4j. Cada noticia y cada entidad debe
tener su propia nota, enlazada con [[wiki-links]].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path

from src.config import DIR_JSON, DIR_VAULT
from src.conocimiento.utilidades import enlace_obsidian, slugify
from src.validacion.validador import ValidadorJSON


class EscritorObsidian(ABC):
    """Contrato para generar la bóveda a partir de JSON validado."""

    @abstractmethod
    def escribir_noticia(self, data: dict) -> Path:
        """Crea obsidian_vault/Noticias/{id_noticia}.md con frontmatter y enlaces."""

    @abstractmethod
    def escribir_entidades(self, noticias: list[dict]) -> None:
        """Agrega notas de delitos, personas, organizaciones, lugares y objetos."""

    @abstractmethod
    def escribir_indice(self, noticias: list[dict]) -> Path:
        """Crea obsidian_vault/00_Indice.md."""

    @abstractmethod
    def escribir_vault(self, noticias: list[dict]) -> None:
        """Orquesta noticia + entidades + índice."""


class EscritorVaultObsidian(EscritorObsidian):
    """Implementación objetivo del laboratorio.

    Jerarquía generada:
        obsidian_vault/
        ├── 00_Indice.md
        ├── Noticias/
        ├── Delitos/
        ├── Personas/
        ├── Organizaciones/
        ├── Lugares/
        ├── Objetos/
        └── Relaciones/
    """

    CARPETAS = (
        "Noticias",
        "Delitos",
        "Personas",
        "Organizaciones",
        "Lugares",
        "Objetos",
        "Relaciones",
    )

    def __init__(self, vault: Path = DIR_VAULT, dir_json: Path = DIR_JSON) -> None:
        self.vault = vault
        self.dir_json = dir_json
        self._validador = ValidadorJSON()

    # -- utilidades internas -------------------------------------------------

    def _asegurar_carpetas(self) -> None:
        self.vault.mkdir(parents=True, exist_ok=True)
        for carpeta in self.CARPETAS:
            (self.vault / carpeta).mkdir(parents=True, exist_ok=True)

    def _enlace_entidad(self, nombre: str) -> str:
        """Wiki-link estable: usa el slug para que nunca se rompa el enlace."""
        return enlace_obsidian(slugify(nombre))

    def _cargar_noticias(self) -> list[dict]:
        """Recorre data/json/*.json, valida cada archivo y deduplica por id_noticia.

        Ordenar alfabéticamente antes de deduplicar hace que N001.json (dato real)
        gane sobre ejemplo_N001.json (fixture de prueba) si ambos existen.
        """
        vistas: dict[str, dict] = {}
        for ruta in sorted(self.dir_json.glob("*.json")):
            try:
                data = self._validador.validar(ruta)
            except ValueError as exc:
                print(f"    [obsidian] {ruta.name} inválido, se omite: {exc}")
                continue
            vistas.setdefault(data["id_noticia"], data)
        return list(vistas.values())

    # -- noticias --------------------------------------------------------------

    def escribir_noticia(self, data: dict) -> Path:
        (self.vault / "Noticias").mkdir(parents=True, exist_ok=True)
        id_noticia = data["id_noticia"]
        ruta = self.vault / "Noticias" / f"{id_noticia}.md"

        lineas = [
            "---",
            f"id: {id_noticia}",
            f"fecha_publicacion: {data.get('fecha_publicacion')}",
            f"fuente: {data.get('fuente')}",
            f"url: {data.get('url')}",
            "---",
            "",
            f"# {data.get('titulo') or id_noticia}",
            "",
            "## Resumen",
            data.get("resumen") or "_Sin resumen._",
            "",
            "## Delitos",
        ]
        delitos = data.get("delitos") or []
        lineas += [f"- {self._enlace_entidad(d)}" for d in delitos] or ["_Sin delitos registrados._"]
        lineas += ["", "## Personas"]

        personas = data.get("personas") or []
        if personas:
            for persona in personas:
                nombre = persona.get("nombre") or "Desconocido"
                rol = persona.get("rol") or "rol no especificado"
                lineas.append(f"- {self._enlace_entidad(nombre)} - {rol}")
        else:
            lineas.append("_Sin personas registradas._")
        lineas += ["", "## Organizaciones"]

        organizaciones = data.get("organizaciones") or []
        lineas += [f"- {self._enlace_entidad(o)}" for o in organizaciones] or ["_Sin organizaciones registradas._"]
        lineas += ["", "## Lugares"]

        lugares = data.get("lugares") or []
        lineas += [f"- {self._enlace_entidad(l)}" for l in lugares] or ["_Sin lugares registrados._"]
        lineas += ["", "## Objetos"]

        objetos = data.get("objetos") or []
        if objetos:
            for objeto in objetos:
                nombre = objeto.get("nombre") or objeto.get("tipo") or "objeto"
                detalle = []
                if objeto.get("tipo"):
                    detalle.append(objeto["tipo"])
                if objeto.get("cantidad") is not None:
                    detalle.append(f"{objeto['cantidad']} {objeto.get('unidad') or ''}".strip())
                sufijo = f" ({', '.join(detalle)})" if detalle else ""
                lineas.append(f"- {self._enlace_entidad(nombre)}{sufijo}")
        else:
            lineas.append("_Sin objetos registrados._")
        lineas += ["", "## Relaciones"]

        relaciones = data.get("relaciones") or []
        if relaciones:
            for rel in relaciones:
                origen = self._enlace_entidad(rel.get("origen", ""))
                destino = self._enlace_entidad(rel.get("destino", ""))
                tipo = rel.get("tipo") or "RELACIONADO_CON"
                lineas.append(f"- {origen} -- {tipo} --> {destino}")
        else:
            lineas.append("_Sin relaciones registradas._")
        lineas.append("")

        ruta.write_text("\n".join(lineas), encoding="utf-8")
        return ruta

    # -- entidades ---------------------------------------------------------

    def escribir_entidades(self, noticias: list[dict]) -> None:
        self._asegurar_carpetas()

        delitos: dict[str, dict] = defaultdict(
            lambda: {"noticias": set(), "personas": set(), "organizaciones": set(), "lugares": set()}
        )
        personas: dict[str, dict] = defaultdict(
            lambda: {"noticias": set(), "roles": defaultdict(set), "delitos": set(), "organizaciones": set()}
        )
        organizaciones: dict[str, dict] = defaultdict(
            lambda: {"noticias": set(), "personas": set(), "delitos": set(), "lugares": set()}
        )
        lugares: dict[str, dict] = defaultdict(
            lambda: {"noticias": set(), "delitos": set(), "organizaciones": set(), "personas": set()}
        )
        objetos: dict[str, dict] = defaultdict(lambda: {"noticias": set(), "tipo": None, "delitos": set()})
        relaciones: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

        for data in noticias:
            nid = data["id_noticia"]
            lista_delitos = data.get("delitos") or []
            lista_personas = data.get("personas") or []
            lista_organizaciones = data.get("organizaciones") or []
            lista_lugares = data.get("lugares") or []
            lista_objetos = data.get("objetos") or []
            nombres_personas = [p["nombre"] for p in lista_personas if p.get("nombre")]

            for delito in lista_delitos:
                reg = delitos[delito]
                reg["noticias"].add(nid)
                reg["personas"].update(nombres_personas)
                reg["organizaciones"].update(lista_organizaciones)
                reg["lugares"].update(lista_lugares)

            for persona in lista_personas:
                nombre = persona.get("nombre")
                if not nombre:
                    continue
                reg = personas[nombre]
                reg["noticias"].add(nid)
                reg["roles"][persona.get("rol") or "sin rol especificado"].add(nid)
                reg["delitos"].update(lista_delitos)
                reg["organizaciones"].update(lista_organizaciones)

            for org in lista_organizaciones:
                reg = organizaciones[org]
                reg["noticias"].add(nid)
                reg["personas"].update(nombres_personas)
                reg["delitos"].update(lista_delitos)
                reg["lugares"].update(lista_lugares)

            for lugar in lista_lugares:
                reg = lugares[lugar]
                reg["noticias"].add(nid)
                reg["delitos"].update(lista_delitos)
                reg["organizaciones"].update(lista_organizaciones)
                reg["personas"].update(nombres_personas)

            for objeto in lista_objetos:
                nombre_obj = objeto.get("nombre")
                if not nombre_obj:
                    continue
                reg = objetos[nombre_obj]
                reg["noticias"].add(nid)
                if objeto.get("tipo"):
                    reg["tipo"] = objeto["tipo"]
                reg["delitos"].update(lista_delitos)

            for rel in data.get("relaciones") or []:
                tipo = rel.get("tipo") or "RELACIONADO_CON"
                relaciones[tipo].append((rel.get("origen", ""), rel.get("destino", ""), nid))

        self._escribir_notas_entidad(
            carpeta="Delitos",
            tipo_singular="Delito",
            indice=delitos,
            secciones={
                "Noticias relacionadas": ("noticias", True),
                "Personas relacionadas": ("personas", False),
                "Organizaciones relacionadas": ("organizaciones", False),
                "Lugares": ("lugares", False),
            },
        )
        self._escribir_notas_entidad(
            carpeta="Organizaciones",
            tipo_singular="Organización",
            indice=organizaciones,
            secciones={
                "Noticias relacionadas": ("noticias", True),
                "Personas relacionadas": ("personas", False),
                "Delitos relacionados": ("delitos", False),
                "Lugares": ("lugares", False),
            },
        )
        self._escribir_notas_entidad(
            carpeta="Lugares",
            tipo_singular="Lugar",
            indice=lugares,
            secciones={
                "Noticias relacionadas": ("noticias", True),
                "Delitos relacionados": ("delitos", False),
                "Organizaciones relacionadas": ("organizaciones", False),
                "Personas relacionadas": ("personas", False),
            },
        )
        self._escribir_notas_persona(personas)
        self._escribir_notas_objeto(objetos)
        self._escribir_notas_relacion(relaciones)

    def _escribir_notas_entidad(
        self,
        carpeta: str,
        tipo_singular: str,
        indice: dict[str, dict],
        secciones: dict[str, tuple[str, bool]],
    ) -> None:
        for nombre, datos in indice.items():
            ruta = self.vault / carpeta / f"{slugify(nombre)}.md"
            lineas = [f"# {nombre}", "", f"Tipo: {tipo_singular}", ""]
            for titulo, (clave, es_noticia) in secciones.items():
                valores = sorted(datos.get(clave) or [])
                lineas.append(f"## {titulo}")
                if valores:
                    for valor in valores:
                        enlace = enlace_obsidian(valor) if es_noticia else self._enlace_entidad(valor)
                        lineas.append(f"- {enlace}")
                else:
                    lineas.append("_Sin datos._")
                lineas.append("")
            ruta.write_text("\n".join(lineas), encoding="utf-8")

    def _escribir_notas_persona(self, indice: dict[str, dict]) -> None:
        for nombre, datos in indice.items():
            ruta = self.vault / "Personas" / f"{slugify(nombre)}.md"
            lineas = [f"# {nombre}", "", "Tipo: Persona", "", "## Noticias donde aparece"]

            noticias_ids = sorted(datos["noticias"])
            lineas += [f"- {enlace_obsidian(nid)}" for nid in noticias_ids] or ["_Sin datos._"]
            lineas += ["", "## Rol observado"]

            roles = datos["roles"]
            if roles:
                for rol, nids in sorted(roles.items()):
                    nids_fmt = ", ".join(enlace_obsidian(n) for n in sorted(nids))
                    lineas.append(f"- {rol}: {nids_fmt}")
            else:
                lineas.append("_Sin datos._")
            lineas += ["", "## Delitos asociados"]

            delitos = sorted(datos["delitos"])
            lineas += [f"- {self._enlace_entidad(d)}" for d in delitos] or ["_Sin datos._"]
            lineas += ["", "## Organizaciones relacionadas"]

            orgs = sorted(datos["organizaciones"])
            lineas += [f"- {self._enlace_entidad(o)}" for o in orgs] or ["_Sin datos._"]
            lineas.append("")

            ruta.write_text("\n".join(lineas), encoding="utf-8")

    def _escribir_notas_objeto(self, indice: dict[str, dict]) -> None:
        for nombre, datos in indice.items():
            ruta = self.vault / "Objetos" / f"{slugify(nombre)}.md"
            lineas = [
                f"# {nombre}",
                "",
                f"Tipo: {datos.get('tipo') or 'Objeto'}",
                "",
                "## Noticias relacionadas",
            ]
            noticias_ids = sorted(datos["noticias"])
            lineas += [f"- {enlace_obsidian(nid)}" for nid in noticias_ids] or ["_Sin datos._"]
            lineas += ["", "## Delitos relacionados"]

            delitos = sorted(datos["delitos"])
            lineas += [f"- {self._enlace_entidad(d)}" for d in delitos] or ["_Sin datos._"]
            lineas.append("")

            ruta.write_text("\n".join(lineas), encoding="utf-8")

    def _escribir_notas_relacion(self, indice: dict[str, list[tuple[str, str, str]]]) -> None:
        for tipo, instancias in indice.items():
            ruta = self.vault / "Relaciones" / f"{slugify(tipo)}.md"
            lineas = [f"# {tipo}", "", "Tipo: Relación", "", "## Instancias"]
            if instancias:
                for origen, destino, nid in instancias:
                    lineas.append(
                        f"- {self._enlace_entidad(origen)} -- {tipo} --> "
                        f"{self._enlace_entidad(destino)} ({enlace_obsidian(nid)})"
                    )
            else:
                lineas.append("_Sin datos._")
            lineas.append("")
            ruta.write_text("\n".join(lineas), encoding="utf-8")

    # -- índice y orquestación ----------------------------------------------

    def escribir_indice(self, noticias: list[dict]) -> Path:
        self.vault.mkdir(parents=True, exist_ok=True)
        ruta = self.vault / "00_Indice.md"

        delitos = sorted({d for n in noticias for d in (n.get("delitos") or [])})
        personas = sorted(
            {p["nombre"] for n in noticias for p in (n.get("personas") or []) if p.get("nombre")}
        )
        organizaciones = sorted({o for n in noticias for o in (n.get("organizaciones") or [])})
        lugares = sorted({l for n in noticias for l in (n.get("lugares") or [])})
        objetos = sorted(
            {o["nombre"] for n in noticias for o in (n.get("objetos") or []) if o.get("nombre")}
        )

        lineas = ["# Índice — Noticias delictuales", "", "## Noticias"]
        for data in sorted(noticias, key=lambda d: d["id_noticia"]):
            titulo = data.get("titulo") or data["id_noticia"]
            lineas.append(f"- {enlace_obsidian(data['id_noticia'])} — {titulo}")
        if not noticias:
            lineas.append("_Sin noticias procesadas._")
        lineas.append("")

        for etiqueta, valores in (
            ("Delitos", delitos),
            ("Personas", personas),
            ("Organizaciones", organizaciones),
            ("Lugares", lugares),
            ("Objetos", objetos),
        ):
            lineas.append(f"## {etiqueta}")
            lineas += [f"- {self._enlace_entidad(v)}" for v in valores] or ["_Sin datos._"]
            lineas.append("")

        ruta.write_text("\n".join(lineas), encoding="utf-8")
        return ruta

    def escribir_vault(self, noticias: list[dict]) -> None:
        self._asegurar_carpetas()
        if not noticias:
            noticias = self._cargar_noticias()
        for data in noticias:
            self.escribir_noticia(data)
        self.escribir_entidades(noticias)
        self.escribir_indice(noticias)
        print(f"  Vault escrito en {self.vault} ({len(noticias)} noticias).")
