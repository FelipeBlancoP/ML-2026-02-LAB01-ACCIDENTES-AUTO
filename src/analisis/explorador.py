"""Data Understanding sobre el corpus estructurado.

Cada método calcula un resultado (pandas), guarda su gráfico en
data/graficos/ y redacta una interpretación en texto plano con los
números reales que arrojó el corpus — nunca un texto genérico. Todas
las interpretaciones se juntan en docs/data_understanding.md.
"""

from __future__ import annotations

import csv
import os
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config import DIR_DOCS, DIR_GRAFICOS, DIR_JSON, RUTA_URLS
from src.validacion.validador import ValidadorJSON

CAMPOS_ESCALARES = ["fecha_publicacion", "titulo", "fuente", "url", "resumen"]
CAMPOS_LISTA = ["delitos", "personas", "organizaciones", "lugares", "objetos", "relaciones"]

# Fusiona variantes de escritura o categorías que el equipo considera
# equivalentes para este corpus. "Asalto" queda tal cual, sin fusionar.
# Se compara en minúsculas.
NORMALIZACION_MODALIDAD = {
    "robo de vehículo": "Robo de vehículos",
    "robo con violencia": "Robo con intimidación",
}

# (clave interna, título de sección, nombre de archivo del gráfico o None si no aplica)
SECCIONES_REPORTE = [
    ("resumen_calidad", "Resumen de calidad de datos", None),
    ("noticias_por_fuente", "Noticias por fuente", "noticias_por_fuente.png"),
    ("delitos_frecuentes", "Modalidades más frecuentes", "delitos_frecuentes.png"),
    ("lugares_frecuentes", "Comunas/lugares más frecuentes", "lugares_frecuentes.png"),
    ("campos_faltantes", "Campos faltantes o vacíos", "campos_faltantes.png"),
    ("evolucion_temporal", "Evolución temporal", "evolucion_temporal.png"),
    ("modalidad_por_comuna", "Modalidad de robo por comuna", "modalidad_por_comuna.png"),
    ("entidades_repetidas", "Entidades repetidas (personas y organizaciones)", None),
    ("objetos_por_modalidad", "Objetos asociados por modalidad", "objetos_por_modalidad.png"),
    ("densidad_entidades", "Densidad de entidades por noticia", "densidad_entidades.png"),
]


class ExploradorDatos:
    """Estadísticas, gráficos y reporte de Data Understanding (pandas + matplotlib)."""

    def __init__(
        self,
        dir_json: Path = DIR_JSON,
        dir_graficos: Path = DIR_GRAFICOS,
        dir_docs: Path = DIR_DOCS,
        ruta_urls: Path = RUTA_URLS,
    ) -> None:
        self.dir_json = dir_json
        self.dir_graficos = dir_graficos
        self.dir_docs = dir_docs
        self.ruta_urls = ruta_urls
        self._validador = ValidadorJSON()
        self._interpretaciones: dict[str, str] = {}
        self._tablas_markdown: dict[str, str] = {}

    # -- carga de datos -------------------------------------------------

    def _cargar_noticias(self) -> tuple[list[dict], int]:
        """Recorre data/json/*.json. Devuelve (noticias válidas, cantidad de JSON inválidos).

        Deduplica por id_noticia: el orden alfabético hace que N001.json (dato
        real) gane sobre ejemplo_N001.json (fixture de prueba) si ambos existen.
        """
        vistas: dict[str, dict] = {}
        invalidos = 0
        for ruta in sorted(self.dir_json.glob("*.json")):
            try:
                data = self._validador.validar(ruta)
            except ValueError as exc:
                invalidos += 1
                print(f"    [analizar] {ruta.name} inválido, se omite: {exc}")
                continue
            vistas.setdefault(data["id_noticia"], data)
        return list(vistas.values()), invalidos

    def _dataframe(self) -> pd.DataFrame:
        noticias, _ = self._cargar_noticias()
        return pd.DataFrame(noticias)

    def _guardar(self, ax, nombre_archivo: str) -> Path:
        self.dir_graficos.mkdir(parents=True, exist_ok=True)
        fig = ax.get_figure()
        fig.tight_layout()
        ruta = self.dir_graficos / nombre_archivo
        fig.savefig(ruta, dpi=120)
        plt.close(fig)
        print(f"    Gráfico guardado en {ruta}")
        return ruta

    def _registrar(self, clave: str, texto: str) -> None:
        self._interpretaciones[clave] = texto
        print(f"    {texto}")

    def _normalizar_modalidad(self, delito: str) -> str:
        """Fusiona solo variantes de escritura del mismo término (ver NORMALIZACION_MODALIDAD)."""
        return NORMALIZACION_MODALIDAD.get((delito or "").strip().lower(), delito)

    def _tabla_markdown(self, df: pd.DataFrame, max_filas: int = 20) -> str:
        if df.empty:
            return "_Sin datos._"
        columnas = list(df.columns)
        encabezado = "| " + " | ".join(columnas) + " |"
        separador = "| " + " | ".join(["---"] * len(columnas)) + " |"
        filas = [
            "| " + " | ".join(str(fila[c]) for c in columnas) + " |"
            for _, fila in df.head(max_filas).iterrows()
        ]
        tabla = "\n".join([encabezado, separador, *filas])
        if len(df) > max_filas:
            tabla += f"\n\n_(mostrando {max_filas} de {len(df)} filas)_"
        return tabla

    # -- métodos mínimos pedidos por la guía --------------------------------

    def noticias_por_fuente(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("noticias_por_fuente", "Sin noticias para graficar (noticias_por_fuente).")
            return pd.Series(dtype=int)
        conteo = df["fuente"].fillna("Sin fuente").value_counts()
        ax = conteo.plot(kind="bar", title="Noticias por fuente", color="#4C72B0")
        ax.set_xlabel("Fuente")
        ax.set_ylabel("Cantidad de noticias")
        self._guardar(ax, "noticias_por_fuente.png")
        top = conteo.index[0]
        segunda = f", seguida por '{conteo.index[1]}' con {conteo.iloc[1]}" if len(conteo) > 1 else ""
        texto = (
            f"El corpus reúne {len(df)} noticias de {len(conteo)} fuentes distintas. "
            f"'{top}' es la fuente con más cobertura ({conteo.iloc[0]}/{len(df)}, "
            f"{conteo.iloc[0] / len(df):.0%} del total){segunda}. "
            f"{int((conteo == 1).sum())} fuentes aportan una sola noticia, lo que indica que el corpus "
            "depende de un número reducido de medios más que de una muestra ampliamente distribuida."
        )
        self._registrar("noticias_por_fuente", texto)
        return conteo

    def delitos_frecuentes(self, top: int = 10) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("delitos_frecuentes", "Sin noticias para graficar (delitos_frecuentes).")
            return pd.Series(dtype=int)
        conteo_total = Counter(
            self._normalizar_modalidad(d) for lista in df["delitos"] for d in (lista or [])
        )
        if not conteo_total:
            self._registrar("delitos_frecuentes", "Ninguna noticia tiene delitos/modalidades registradas.")
            return pd.Series(dtype=int)
        conteo = pd.Series(conteo_total).sort_values(ascending=False).head(top)
        ax = conteo.plot(kind="bar", title=f"Top {min(top, len(conteo))} modalidades", color="#C44E52")
        ax.set_xlabel("Modalidad")
        ax.set_ylabel("Menciones")
        self._guardar(ax, "delitos_frecuentes.png")
        total_menciones = sum(conteo_total.values())
        texto = (
            f"Se registraron {total_menciones} menciones de modalidad en {len(df)} noticias, repartidas en "
            f"{len(conteo_total)} modalidades distintas. '{conteo.index[0]}' es la más mencionada "
            f"({conteo.iloc[0]} veces, {conteo.iloc[0] / total_menciones:.0%} del total de menciones)"
            + (
                f", seguida por '{conteo.index[1]}' ({conteo.iloc[1]})."
                if len(conteo) > 1
                else "."
            )
            + " Esto refleja el sesgo de búsqueda del corpus (URLs semilla centradas en portonazo/encerrona), "
            "no necesariamente la proporción real de cada modalidad a nivel país."
        )
        self._registrar("delitos_frecuentes", texto)
        return conteo

    def lugares_frecuentes(self, top: int = 10) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("lugares_frecuentes", "Sin noticias para graficar (lugares_frecuentes).")
            return pd.Series(dtype=int)
        conteo_total = Counter(l for lista in df["lugares"] for l in (lista or []))
        if not conteo_total:
            self._registrar("lugares_frecuentes", "Ninguna noticia tiene lugares registrados.")
            return pd.Series(dtype=int)
        conteo = pd.Series(conteo_total).sort_values(ascending=False).head(top)
        ax = conteo.plot(kind="barh", title=f"Top {min(top, len(conteo))} lugares", color="#55A868")
        ax.invert_yaxis()
        ax.set_xlabel("Menciones")
        ax.set_ylabel("Lugar")
        self._guardar(ax, "lugares_frecuentes.png")
        conteo_completo = pd.Series(conteo_total)
        mencionados_una_vez = int((conteo_completo == 1).sum())
        texto = (
            f"Se mencionaron {len(conteo_total)} lugares distintos en {len(df)} noticias. "
            f"'{conteo.index[0]}' concentra la mayor cantidad de menciones ({conteo.iloc[0]})"
            + (f", seguido por '{conteo.index[1]}' ({conteo.iloc[1]})." if len(conteo) > 1 else ".")
            + f" En total, {mencionados_una_vez} lugares aparecen mencionados una sola vez, lo que "
            "muestra alta dispersión geográfica pese a la concentración en el lugar más nombrado."
        )
        self._registrar("lugares_frecuentes", texto)
        return conteo

    def campos_faltantes(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("campos_faltantes", "Sin noticias para graficar (campos_faltantes).")
            return pd.Series(dtype=float)
        total = len(df)
        porcentajes = {}
        for campo in CAMPOS_ESCALARES:
            porcentajes[campo] = df[campo].isna().sum() / total * 100
        for campo in CAMPOS_LISTA:
            porcentajes[campo] = df[campo].apply(lambda x: not x).sum() / total * 100
        conteo = pd.Series(porcentajes).sort_values(ascending=False)
        ax = conteo.plot(kind="barh", title="Campos faltantes o vacíos (%)", color="#8172B2")
        ax.invert_yaxis()
        ax.set_xlabel("% de noticias con el campo vacío/null")
        self._guardar(ax, "campos_faltantes.png")
        peor = conteo.index[0]
        campos_sin_faltantes = int((conteo == 0).sum())
        texto = (
            f"Sobre {total} noticias, '{peor}' es el campo con más vacíos: {conteo.iloc[0]:.0f}% "
            f"({round(conteo.iloc[0] / 100 * total)} noticias) no lo registran. "
            f"{campos_sin_faltantes} de {len(conteo)} campos del contrato están completos en el 100% de "
            "las noticias (nunca aparecen vacíos), mientras que los campos de entidades (personas, objetos) "
            "son los que más se pierden, coherente con que muchas noticias policiales no identifican "
            "sospechosos por nombre ni detallan el arma u objeto usado."
        )
        self._registrar("campos_faltantes", texto)
        return conteo

    def evolucion_temporal(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("evolucion_temporal", "Sin noticias para graficar (evolucion_temporal).")
            return pd.Series(dtype=int)
        fechas = pd.to_datetime(df["fecha_publicacion"], errors="coerce")
        validas = fechas.dropna()
        if validas.empty:
            self._registrar(
                "evolucion_temporal",
                "Ninguna noticia tiene fecha_publicacion utilizable; no se generó el gráfico.",
            )
            return pd.Series(dtype=int)
        conteo = validas.dt.to_period("M").value_counts().sort_index()
        conteo.index = conteo.index.astype(str)
        ax = conteo.plot(kind="line", marker="o", title="Noticias por mes")
        ax.set_xlabel("Mes")
        ax.set_ylabel("Cantidad de noticias")
        self._guardar(ax, "evolucion_temporal.png")
        mes_top = conteo.idxmax()
        texto = (
            f"Solo {len(validas)}/{len(df)} noticias ({len(validas) / len(df):.0%}) tienen fecha de "
            f"publicación utilizable, distribuidas en {len(conteo)} meses distintos entre "
            f"{conteo.index.min()} y {conteo.index.max()}. El mes con más noticias es {mes_top} "
            f"({int(conteo.max())} noticias). La baja cobertura temporal ({len(validas)} de {len(df)}) "
            "limita cualquier lectura de tendencia: no alcanza para distinguir estacionalidad real de "
            "ruido en la extracción de fechas."
        )
        self._registrar("evolucion_temporal", texto)
        return conteo

    # -- análisis adicionales solicitados ------------------------------------

    def modalidad_por_comuna(self) -> pd.DataFrame:
        df = self._dataframe()
        if df.empty:
            self._registrar("modalidad_por_comuna", "Sin noticias para cruzar modalidad por comuna.")
            return pd.DataFrame()

        filas = [
            {
                "comuna": (row["lugares"] or [None])[0] or "Sin comuna",
                "modalidad": self._normalizar_modalidad(delito),
            }
            for _, row in df.iterrows()
            for delito in (row["delitos"] or [])
        ]
        if not filas:
            self._registrar(
                "modalidad_por_comuna",
                "Ninguna noticia tiene a la vez comuna y modalidad registradas; no se pudo cruzar.",
            )
            return pd.DataFrame()

        tabla = pd.DataFrame(filas).pivot_table(
            index="comuna", columns="modalidad", aggfunc="size", fill_value=0
        )
        tabla = tabla.loc[tabla.sum(axis=1).sort_values(ascending=False).index]
        ax = tabla.plot(kind="bar", title="Modalidad de robo por comuna")
        ax.set_xlabel("Comuna")
        ax.set_ylabel("Casos")
        self._guardar(ax, "modalidad_por_comuna.png")

        total_casos = int(tabla.values.sum())
        comuna_top = tabla.sum(axis=1).idxmax()
        casos_top = int(tabla.sum(axis=1).max())
        modalidad_dominante = tabla.loc[comuna_top].idxmax()
        casos_modalidad_dominante = int(tabla.loc[comuna_top].max())
        comunas_una_modalidad = int((tabla.astype(bool).sum(axis=1) == 1).sum())
        texto = (
            f"Se cruzaron {total_casos} pares comuna-modalidad en {len(tabla)} comunas. "
            f"'{comuna_top}' concentra la mayor cantidad de casos ({casos_top} de {total_casos}), "
            f"dominados por '{modalidad_dominante}' ({casos_modalidad_dominante} de {casos_top} casos "
            f"de esa comuna). {comunas_una_modalidad} de {len(tabla)} comunas ({comunas_una_modalidad / len(tabla):.0%}) "
            "solo registran una modalidad. Con este tamaño de corpus (pocos casos por comuna) esa "
            "concentración puede deberse a qué noticias se capturaron y no a un patrón delictual real "
            "por zona; para una conclusión sólida se necesitaría más volumen por comuna."
        )
        self._registrar("modalidad_por_comuna", texto)
        return tabla

    def entidades_repetidas(self) -> pd.DataFrame:
        df = self._dataframe()
        if df.empty:
            self._registrar("entidades_repetidas", "Sin noticias para buscar entidades repetidas.")
            return pd.DataFrame()

        registros: dict[tuple[str, str], dict] = {}
        for _, row in df.iterrows():
            nid = row["id_noticia"]
            for persona in row["personas"] or []:
                nombre = (persona.get("nombre") or "").strip()
                if not nombre:
                    continue
                clave = ("persona", nombre.lower())
                reg = registros.setdefault(clave, {"nombre": nombre, "tipo": "persona", "ids": set()})
                reg["ids"].add(nid)
            for org in row["organizaciones"] or []:
                nombre = (org or "").strip()
                if not nombre:
                    continue
                clave = ("organizacion", nombre.lower())
                reg = registros.setdefault(clave, {"nombre": nombre, "tipo": "organizacion", "ids": set()})
                reg["ids"].add(nid)

        filas = [
            {
                "nombre": reg["nombre"],
                "tipo": reg["tipo"],
                "cantidad_noticias": len(reg["ids"]),
                "ids_noticias": ", ".join(sorted(reg["ids"])),
            }
            for reg in registros.values()
        ]
        tabla = (
            pd.DataFrame(filas)
            .sort_values(["cantidad_noticias", "nombre"], ascending=[False, True])
            .reset_index(drop=True)
        )
        self._tablas_markdown["entidades_repetidas"] = self._tabla_markdown(tabla)

        repetidas = tabla[tabla["cantidad_noticias"] > 1]
        if repetidas.empty:
            texto = (
                f"Se catalogaron {len(tabla)} entidades únicas (personas y organizaciones) tras normalizar "
                "nombres a minúsculas y sin espacios extra. Ninguna aparece en más de una noticia: no hay "
                "evidencia de reincidencia ni de una misma persona/organización detrás de más de un caso en "
                "este corpus. Esto es consistente con que la mayoría de las noticias no identifica a los "
                "responsables por nombre propio, solo a víctimas o voceros policiales sin repetirse entre casos."
            )
        else:
            top = repetidas.iloc[0]
            explicacion = (
                "corresponde a una institución policial (Carabineros/PDI) citada como fuente en distintos "
                "casos, no necesariamente al mismo hecho delictual repetido"
                if top["tipo"] == "organizacion"
                else "conviene revisarla manualmente para confirmar si es la misma persona en distintos "
                "hechos o una coincidencia de nombre"
            )
            texto = (
                f"De {len(tabla)} entidades únicas, {len(repetidas)} ({len(repetidas) / len(tabla):.0%}) "
                f"aparecen en más de una noticia. La más repetida es '{top['nombre']}' ({top['tipo']}), "
                f"presente en {top['cantidad_noticias']} noticias: {top['ids_noticias']}. Esta entidad "
                f"{explicacion}."
            )
        self._registrar("entidades_repetidas", texto)
        return tabla

    def objetos_por_modalidad(self) -> pd.DataFrame:
        df = self._dataframe()
        if df.empty:
            self._registrar("objetos_por_modalidad", "Sin noticias para cruzar objetos por modalidad.")
            return pd.DataFrame()

        filas = [
            {
                "modalidad": self._normalizar_modalidad(delito),
                "tipo_objeto": objeto.get("tipo") or "sin_tipo",
            }
            for _, row in df.iterrows()
            for delito in (row["delitos"] or [])
            for objeto in (row["objetos"] or [])
        ]
        if not filas:
            self._registrar(
                "objetos_por_modalidad",
                "Ninguna noticia registra a la vez modalidad y objetos; no se pudo cruzar.",
            )
            return pd.DataFrame()

        tabla = pd.DataFrame(filas).pivot_table(
            index="modalidad", columns="tipo_objeto", aggfunc="size", fill_value=0
        )
        ax = tabla.plot(kind="bar", title="Objetos asociados por modalidad de robo")
        ax.set_xlabel("Modalidad")
        ax.set_ylabel("Menciones")
        self._guardar(ax, "objetos_por_modalidad.png")

        total = int(tabla.values.sum())
        modalidad_top = tabla.sum(axis=1).idxmax()
        tipo_top_en_modalidad = tabla.loc[modalidad_top].idxmax()
        cantidad_top = int(tabla.loc[modalidad_top].max())
        tipo_general = tabla.sum(axis=0).idxmax()
        cantidad_general = int(tabla.sum(axis=0).max())
        texto = (
            f"Se registraron {total} combinaciones modalidad-objeto entre {len(tabla)} modalidades y "
            f"{tabla.shape[1]} tipos de objeto distintos. En '{modalidad_top}' predomina el objeto tipo "
            f"'{tipo_top_en_modalidad}' ({cantidad_top} de {int(tabla.loc[modalidad_top].sum())} menciones "
            f"de esa modalidad). A nivel general, '{tipo_general}' es el tipo de objeto más mencionado en "
            f"todas las modalidades ({cantidad_general} de {total} menciones), reflejando que las noticias "
            "policiales suelen describir con más detalle el arma usada para intimidar que otros elementos "
            "(vehículo sustraído, herramientas, etc.)."
        )
        self._registrar("objetos_por_modalidad", texto)
        return tabla

    def densidad_entidades(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            self._registrar("densidad_entidades", "Sin noticias para graficar densidad_entidades.")
            return pd.Series(dtype=int)

        totales = df.apply(
            lambda row: len(row["personas"] or [])
            + len(row["organizaciones"] or [])
            + len(row["objetos"] or [])
            + len(row["relaciones"] or []),
            axis=1,
        )
        totales.index = df["id_noticia"].to_numpy()

        maximo = int(totales.max())
        ax = totales.plot(
            kind="hist",
            bins=range(0, maximo + 2),
            title="Densidad de entidades por noticia",
            color="#4C72B0",
            rwidth=0.9,
        )
        ax.set_xlabel("Entidades extraídas (personas + organizaciones + objetos + relaciones)")
        ax.set_ylabel("Cantidad de noticias")
        self._guardar(ax, "densidad_entidades.png")

        umbral = 3
        pobres = totales[totales <= umbral]
        ids_pobres = ", ".join(sorted(pobres.index.tolist()))
        texto = (
            f"El promedio de entidades extraídas por noticia es {totales.mean():.1f} "
            f"(mínimo {int(totales.min())}, máximo {maximo}) sobre {len(totales)} noticias. "
            f"{len(pobres)} noticias ({len(pobres) / len(totales):.0%}) tienen {umbral} entidades o menos: "
            f"{ids_pobres}. Conviene auditar manualmente esas noticias para confirmar si la extracción "
            "pobre se debe a texto fuente corto o poco explícito (por ejemplo páginas centradas en video, "
            "con solo el título y un párrafo) o a un fallo real del proceso de extracción."
        )
        self._registrar("densidad_entidades", texto)
        return totales

    # -- calidad de datos --------------------------------------------------

    def _leer_urls(self) -> list[dict]:
        if not self.ruta_urls.exists():
            return []
        with self.ruta_urls.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))

    def resumen_calidad(self) -> dict:
        urls = self._leer_urls()
        noticias, invalidos = self._cargar_noticias()

        urls_vistas = Counter(fila["url"] for fila in urls if fila.get("url"))
        duplicadas = sum(1 for cantidad in urls_vistas.values() if cantidad > 1)

        ids_url = {fila["id_noticia"] for fila in urls}
        ids_json = {n["id_noticia"] for n in noticias}
        sin_json = ids_url - ids_json

        resumen = {
            "noticias_en_urls_csv": len(urls),
            "urls_duplicadas": duplicadas,
            "json_validos": len(noticias),
            "json_invalidos": invalidos,
            "sin_extraer_o_capturar": len(sin_json),
        }
        texto = (
            f"El corpus tiene {resumen['noticias_en_urls_csv']} noticias registradas en data/urls.csv, de "
            f"las cuales {resumen['json_validos']} cuentan con JSON válido y {resumen['sin_extraer_o_capturar']} "
            "aún no han sido capturadas o extraídas. Se detectaron "
            f"{resumen['urls_duplicadas']} URLs duplicadas y {resumen['json_invalidos']} archivos JSON "
            "inválidos en data/json/."
        )
        self._registrar("resumen_calidad", texto)
        return resumen

    # -- reporte ------------------------------------------------------------

    def generar_reporte(self) -> Path:
        self.dir_docs.mkdir(parents=True, exist_ok=True)
        ruta = self.dir_docs / "data_understanding.md"
        rel_graficos = Path(os.path.relpath(self.dir_graficos, self.dir_docs))

        lineas = [
            "# Data Understanding — Noticias de robo de vehículos",
            "",
            "Generado automáticamente por `python main.py analizar` "
            "(`src.analisis.explorador.ExploradorDatos`). Cada interpretación se calcula a partir de "
            "los JSON reales en `data/json/` al momento de ejecutar el comando.",
            "",
        ]

        for clave, titulo, nombre_grafico in SECCIONES_REPORTE:
            lineas.append(f"## {titulo}")
            lineas.append("")
            if nombre_grafico and (self.dir_graficos / nombre_grafico).exists():
                ruta_img = (rel_graficos / nombre_grafico).as_posix()
                lineas.append(f"![{titulo}]({ruta_img})")
                lineas.append("")
            if clave in self._tablas_markdown:
                lineas.append(self._tablas_markdown[clave])
                lineas.append("")
            lineas.append(self._interpretaciones.get(clave, "_Sin datos para esta sección._"))
            lineas.append("")

        ruta.write_text("\n".join(lineas), encoding="utf-8")
        print(f"  Reporte guardado en {ruta}")
        return ruta

    # -- orquestación --------------------------------------------------

    def ejecutar(self) -> None:
        """Corre todos los análisis y genera docs/data_understanding.md."""
        print("== Data Understanding ==")
        self.resumen_calidad()

        noticias, _ = self._cargar_noticias()
        if not noticias:
            print("  No hay JSON válidos en data/json/. Ejecute primero: python main.py extraer")
            return

        print("\n-- Noticias por fuente --")
        self.noticias_por_fuente()

        print("\n-- Modalidades más frecuentes --")
        self.delitos_frecuentes()

        print("\n-- Lugares más frecuentes --")
        self.lugares_frecuentes()

        print("\n-- Campos faltantes --")
        self.campos_faltantes()

        print("\n-- Evolución temporal --")
        self.evolucion_temporal()

        print("\n-- Modalidad de robo por comuna --")
        self.modalidad_por_comuna()

        print("\n-- Entidades repetidas --")
        self.entidades_repetidas()

        print("\n-- Objetos por modalidad --")
        self.objetos_por_modalidad()

        print("\n-- Densidad de entidades por noticia --")
        self.densidad_entidades()

        print(f"\nGráficos guardados en {self.dir_graficos}")
        self.generar_reporte()
