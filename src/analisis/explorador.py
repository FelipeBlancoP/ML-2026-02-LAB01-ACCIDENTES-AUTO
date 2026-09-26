"""Data Understanding sobre el corpus estructurado.

Las visualizaciones no son decoración: cada método imprime también una
lectura breve (cobertura, sesgo o calidad) además de guardar el gráfico
en data/graficos/.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.config import DIR_GRAFICOS, DIR_JSON, RUTA_URLS
from src.validacion.validador import ValidadorJSON

CAMPOS_ESCALARES = ["fecha_publicacion", "titulo", "fuente", "url", "resumen"]
CAMPOS_LISTA = ["delitos", "personas", "organizaciones", "lugares", "objetos", "relaciones"]


class ExploradorDatos:
    """Estadísticas y gráficos mínimos del laboratorio (pandas + matplotlib)."""

    def __init__(
        self,
        dir_json: Path = DIR_JSON,
        dir_graficos: Path = DIR_GRAFICOS,
        ruta_urls: Path = RUTA_URLS,
    ) -> None:
        self.dir_json = dir_json
        self.dir_graficos = dir_graficos
        self.ruta_urls = ruta_urls
        self._validador = ValidadorJSON()

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

    # -- visualizaciones --------------------------------------------------

    def noticias_por_fuente(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (noticias_por_fuente).")
            return pd.Series(dtype=int)
        conteo = df["fuente"].fillna("Sin fuente").value_counts()
        ax = conteo.plot(kind="bar", title="Noticias por fuente", color="#4C72B0")
        ax.set_xlabel("Fuente")
        ax.set_ylabel("Cantidad de noticias")
        self._guardar(ax, "noticias_por_fuente.png")
        top = conteo.index[0]
        print(
            f"    Lectura: {len(conteo)} fuentes distintas; '{top}' concentra "
            f"{conteo.iloc[0]}/{len(df)} noticias ({conteo.iloc[0] / len(df):.0%})."
        )
        return conteo

    def delitos_frecuentes(self, top: int = 10) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (delitos_frecuentes).")
            return pd.Series(dtype=int)
        conteo_total = Counter(d for lista in df["delitos"] for d in (lista or []))
        if not conteo_total:
            print("  Ninguna noticia tiene delitos registrados.")
            return pd.Series(dtype=int)
        conteo = pd.Series(conteo_total).sort_values(ascending=False).head(top)
        ax = conteo.plot(kind="bar", title=f"Top {min(top, len(conteo))} delitos", color="#C44E52")
        ax.set_xlabel("Delito")
        ax.set_ylabel("Menciones")
        self._guardar(ax, "delitos_frecuentes.png")
        print(f"    Lectura: '{conteo.index[0]}' es el delito más mencionado ({conteo.iloc[0]} veces).")
        return conteo

    def lugares_frecuentes(self, top: int = 10) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (lugares_frecuentes).")
            return pd.Series(dtype=int)
        conteo_total = Counter(l for lista in df["lugares"] for l in (lista or []))
        if not conteo_total:
            print("  Ninguna noticia tiene lugares registrados.")
            return pd.Series(dtype=int)
        conteo = pd.Series(conteo_total).sort_values(ascending=False).head(top)
        ax = conteo.plot(kind="barh", title=f"Top {min(top, len(conteo))} lugares", color="#55A868")
        ax.invert_yaxis()
        ax.set_xlabel("Menciones")
        ax.set_ylabel("Lugar")
        self._guardar(ax, "lugares_frecuentes.png")
        print(f"    Lectura: '{conteo.index[0]}' concentra la mayor cantidad de menciones ({conteo.iloc[0]}).")
        return conteo

    def entidades_por_noticia(self) -> pd.DataFrame:
        """Cantidad de personas y organizaciones detectadas por noticia."""
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (entidades_por_noticia).")
            return pd.DataFrame()
        conteo = pd.DataFrame(
            {
                "personas": df["personas"].apply(lambda x: len(x or [])).to_numpy(),
                "organizaciones": df["organizaciones"].apply(lambda x: len(x or [])).to_numpy(),
            },
            index=df["id_noticia"].to_numpy(),
        )
        ax = conteo.plot(kind="bar", title="Personas y organizaciones por noticia")
        ax.set_xlabel("Noticia")
        ax.set_ylabel("Cantidad de entidades")
        self._guardar(ax, "entidades_por_noticia.png")
        sin_personas = int((conteo["personas"] == 0).sum())
        print(
            f"    Lectura: {sin_personas}/{len(conteo)} noticias no registran ninguna persona con "
            "nombre explícito (víctimas/testigos sin identificar)."
        )
        return conteo

    def campos_faltantes(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (campos_faltantes).")
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
        print(f"    Lectura: '{peor}' es el campo con más vacíos ({conteo.iloc[0]:.0f}% de las noticias).")
        return conteo

    def evolucion_temporal(self) -> pd.Series:
        df = self._dataframe()
        if df.empty:
            print("  Sin noticias para graficar (evolucion_temporal).")
            return pd.Series(dtype=int)
        fechas = pd.to_datetime(df["fecha_publicacion"], errors="coerce")
        validas = fechas.dropna()
        if validas.empty:
            print("  Ninguna noticia tiene fecha_publicacion utilizable; se omite el gráfico.")
            return pd.Series(dtype=int)
        conteo = validas.dt.to_period("M").value_counts().sort_index()
        conteo.index = conteo.index.astype(str)
        ax = conteo.plot(kind="line", marker="o", title="Noticias por mes")
        ax.set_xlabel("Mes")
        ax.set_ylabel("Cantidad de noticias")
        self._guardar(ax, "evolucion_temporal.png")
        print(
            f"    Lectura: {len(validas)}/{len(df)} noticias tienen fecha utilizable "
            f"({len(validas) / len(df):.0%} de cobertura temporal)."
        )
        return conteo

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
        print("  Resumen de calidad de datos:")
        for clave, valor in resumen.items():
            print(f"    {clave}: {valor}")
        return resumen

    # -- orquestación --------------------------------------------------

    def ejecutar(self) -> None:
        """Corre todas las visualizaciones y el resumen de calidad pedidos en la guía."""
        print("== Data Understanding ==")
        self.resumen_calidad()

        noticias, _ = self._cargar_noticias()
        if not noticias:
            print("  No hay JSON válidos en data/json/. Ejecute primero: python main.py extraer")
            return

        print("\n-- Noticias por fuente --")
        self.noticias_por_fuente()

        print("\n-- Delitos más frecuentes --")
        self.delitos_frecuentes()

        print("\n-- Lugares más frecuentes --")
        self.lugares_frecuentes()

        print("\n-- Personas/organizaciones por noticia --")
        self.entidades_por_noticia()

        print("\n-- Campos faltantes --")
        self.campos_faltantes()

        print("\n-- Evolución temporal --")
        self.evolucion_temporal()

        print(f"\nGráficos guardados en {self.dir_graficos}")
