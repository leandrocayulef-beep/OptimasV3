# -*- coding: utf-8 -*-
"""Fases finales 3 y 4: saneamiento, trazabilidad, KPI y tablero (2007-2025).

Uso desde VS Code/Colab:
    %run fase_final_limpieza_kpis.py

Lee la base provisional de resultados_parquet. Opcionalmente acepta un CSV
`ipc_anual.csv` con columnas `cat_periodo, ipc` (índice anual, misma base).
Los resúmenes provisionales son agregados programa-año y no conservan MRUN
individual; por eso aquí no se inventa una validación de trayectorias MRUN.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path
from typing import Optional

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE_DIR = Path.cwd()
CARPETA_SALIDA = BASE_DIR / "resultados_parquet"
RUTA_ENTRADA = CARPETA_SALIDA / "base_historica_2007_2025_provisional.parquet"
RUTA_FINAL = CARPETA_SALIDA / "base_historica_2007_2025_definitiva.parquet"
RUTA_DICCIONARIO = CARPETA_SALIDA / "diccionario_base_definitiva.json"
RUTA_IPC = CARPETA_SALIDA / "ipc_anual.csv"  # Opcional: cat_periodo, ipc
RUTA_TABLERO = CARPETA_SALIDA / "tablero_tendencias_2007_2025.png"


def _asegurar(df: pd.DataFrame, columna: str, dtype: str = "string") -> None:
    """Crea columnas opcionales con dtype estable para tolerar esquemas antiguos."""
    if columna not in df:
        df[columna] = pd.Series(pd.NA, index=df.index, dtype=dtype)


def sanear_base_historica(
    df_historico: pd.DataFrame,
    ipc: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Sanea agregados programa-año y crea `nuevos_ingresados_definitivo`.

    Admisión: utiliza `ingresantes_corregidos` cuando existe (salida del
    Bloque 9 existente), y si no, los ingresantes identificados solo cuando el
    estado no requiere revisión. Los registros pendientes no se aceptan sin
    evidencia MRUN individual. Duración/arancel: imputación por grupo con
    respaldo global, conservando los valores originales y banderas de imputación.
    """
    try:
        df = df_historico.copy()
        for col in ["codigo_unico", "nomb_carrera", "area_carrera_generica",
                    "nomb_inst", "area_conocimiento", "region_sede",
                    "tipo_inst_2", "estado_conteo", "estado_conteo_corregido"]:
            _asegurar(df, col)
        if "cat_periodo" not in df:
            raise ValueError("Falta columna requerida: cat_periodo")
        df["cat_periodo"] = pd.to_numeric(df["cat_periodo"], errors="coerce").astype("Int64")

        for col in ["dur_total_carr_numerico", "valor_arancel_numerico",
                    "ingresantes_identificados", "ingresantes_corregidos",
                    "registros_ingreso_por_revisar", "registros_sin_mrun"]:
            if col not in df:
                candidato = col.removesuffix("_numerico")
                _asegurar(df, col, "Float64")
                if candidato in df:
                    df[col] = pd.to_numeric(df[candidato], errors="coerce").astype("Float64")
                else:
                    df[col] = pd.Series(pd.NA, index=df.index, dtype="Float64")

        # Reconciliación conservadora. El contador de pendientes agregado no
        # permite comprobar continuidad de una persona; solo se incorpora si
        # el archivo ya trae la corrección auditada y explícita del Bloque 9.
        base_ing = df["ingresantes_corregidos"].combine_first(df["ingresantes_identificados"])
        estado = df["estado_conteo_corregido"].combine_first(df["estado_conteo"]).fillna("")
        es_pendiente = estado.str.contains("Pendiente|revisar", case=False, regex=True, na=False)
        df["nuevos_ingresados_definitivo"] = pd.to_numeric(base_ing, errors="coerce").where(~es_pendiente).astype("Float64")
        # Si existía la variable provisional válida, utilizarla cuando la anterior quedó nula.
        if "nuevos_ingresados_provisional" in df:
            df["nuevos_ingresados_definitivo"] = df["nuevos_ingresados_definitivo"].combine_first(
                pd.to_numeric(df["nuevos_ingresados_provisional"], errors="coerce").astype("Float64")
            )

        # Duración normativa en semestres [4, 16]. Primero se usa el valor
        # numérico diagnosticado y luego se intenta parsear el campo original.
        if "dur_total_carr" in df:
            df["dur_total_carr_numerico"] = df["dur_total_carr_numerico"].combine_first(
                pd.to_numeric(df["dur_total_carr"], errors="coerce").astype("Float64")
            )
        dur = df["dur_total_carr_numerico"]
        df["duracion_imputada"] = (dur.isna() | dur.lt(4) | dur.gt(16)).fillna(True)
        dur_valid = dur.where(dur.between(4, 16))
        grupo_dur = "area_carrera_generica" if dur_valid.groupby(df["area_carrera_generica"]).count().sum() else "nomb_carrera"
        mediana_dur = dur_valid.groupby(df[grupo_dur], dropna=False).transform("median")
        mediana_dur = mediana_dur.fillna(dur_valid.median())
        df["dur_total_carr_definitiva"] = dur.where(dur.between(4, 16), mediana_dur).astype("Float64")

        # Arancel nulo/cero: mediana carrera-institución, luego carrera, luego global.
        if "valor_arancel" in df:
            df["valor_arancel_numerico"] = df["valor_arancel_numerico"].combine_first(
                pd.to_numeric(df["valor_arancel"], errors="coerce").astype("Float64")
            )
        arancel = df["valor_arancel_numerico"]
        valido = arancel.where(arancel.gt(0))
        grupo_ci = df["nomb_carrera"].fillna("") + "|" + df["nomb_inst"].fillna("")
        med_ci = valido.groupby(grupo_ci).transform("median")
        med_c = valido.groupby(df["nomb_carrera"], dropna=False).transform("median")
        imputado = med_ci.fillna(med_c).fillna(valido.median())
        df["arancel_imputado"] = (arancel.isna() | arancel.le(0)).fillna(True)
        df["valor_arancel_definitivo"] = arancel.where(arancel.gt(0), imputado).astype("Float64")

        # El importe real solo se calcula cuando se proporciona IPC válido.
        df["valor_arancel_real"] = pd.Series(pd.NA, index=df.index, dtype="Float64")
        if ipc is not None and not ipc.empty:
            req = {"cat_periodo", "ipc"}
            if not req.issubset(ipc.columns):
                raise ValueError("IPC debe tener columnas cat_periodo e ipc")
            tabla = ipc[["cat_periodo", "ipc"]].copy()
            tabla["cat_periodo"] = pd.to_numeric(tabla["cat_periodo"], errors="coerce").astype("Int64")
            tabla["ipc"] = pd.to_numeric(tabla["ipc"], errors="coerce")
            tabla = tabla.dropna().drop_duplicates("cat_periodo").set_index("cat_periodo")["ipc"]
            anio_base = int(tabla.index.max())
            factor = tabla.get(anio_base) / tabla
            factores = df["cat_periodo"].map(factor)
            df["valor_arancel_real"] = (df["valor_arancel_definitivo"] * factores).astype("Float64")
            df.attrs["ipc_anio_base"] = anio_base

        # Dtypes de extensión para columnas clave.
        for col in ["nomb_carrera", "nomb_inst", "area_conocimiento", "region_sede"]:
            df[col] = df[col].astype("string")
        print(f"Saneamiento completado: {len(df):,} filas; {int(df['nuevos_ingresados_definitivo'].notna().sum()):,} conteos válidos.")
        gc.collect()
        return df
    except Exception as exc:
        print(f"Error en sanear_base_historica: {exc}")
        raise


def armonizar_programas(df: pd.DataFrame) -> pd.DataFrame:
    """Armoniza etiquetas por código y calcula apertura, cierre y ciclo de vida."""
    try:
        out = df.copy()
        out = out.sort_values(["codigo_unico", "cat_periodo"], na_position="last")
        for col in ["nomb_carrera", "nomb_inst", "area_conocimiento", "area_carrera_generica"]:
            if col in out:
                out[f"{col}_armonizado"] = out.groupby("codigo_unico", dropna=False)[col].transform(
                    lambda s: s.dropna().mode().iloc[0] if not s.dropna().mode().empty else pd.NA
                ).astype("string")
        stats = out.groupby("codigo_unico", dropna=False).agg(
            anio_apertura=("cat_periodo", "min"),
            ultimo_anio_observado=("cat_periodo", "max"),
            anios_observados=("cat_periodo", "nunique"),
        )
        stats["anio_cierre_o_pausa"] = stats["ultimo_anio_observado"].where(stats["ultimo_anio_observado"].lt(2025), pd.NA).astype("Int64")
        stats["estado_carrera"] = "Activa"
        stats.loc[stats["anio_apertura"].ge(2020), "estado_carrera"] = "Emergente"
        stats.loc[stats["ultimo_anio_observado"].lt(2025), "estado_carrera"] = "Discontinuada"
        # Vacíos internos: marca discontinuidad/pausa observacional sin inventar filas anuales.
        gaps = out.groupby("codigo_unico")["cat_periodo"].apply(
            lambda s: (int(s.max()) - int(s.min()) + 1) > s.nunique() if s.notna().any() else False
        )
        stats["tiene_vacios_matricula"] = gaps
        out = out.merge(stats.reset_index(), on="codigo_unico", how="left", validate="many_to_one")
        out["anio_apertura"] = out["anio_apertura"].astype("Int64")
        out["anios_observados"] = out["anios_observados"].astype("Int64")
        print(f"Armonización completada: {out['codigo_unico'].nunique():,} códigos de programa.")
        gc.collect()
        return out
    except Exception as exc:
        print(f"Error en armonizar_programas: {exc}")
        raise


def exportar_dataset(df: pd.DataFrame, destino: Path = RUTA_FINAL) -> Path:
    """Exporta Parquet comprimido y diccionario con esquema/tipos."""
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(destino, index=False, compression="snappy")
        diccionario = {
            "archivo": destino.name,
            "filas": int(len(df)),
            "periodo": [2007, 2025],
            "tipos": {str(c): str(t) for c, t in df.dtypes.items()},
            "variables_derivadas": {
                "nuevos_ingresados_definitivo": "Conteo conservador de primer ingreso; requiere revisión donde hay incidencia no auditada a nivel MRUN.",
                "dur_total_carr_definitiva": "Duración en semestres; fuera de [4,16] imputada por mediana de área/carrera.",
                "valor_arancel_definitivo": "Arancel nominal; ceros/nulos imputados por carrera-institución y respaldos.",
                "valor_arancel_real": "Arancel deflactado si se provee IPC anual; NA si no.",
                "anio_apertura": "Primer año observado para codigo_unico.",
                "anio_cierre_o_pausa": "Último año observado si anterior a 2025.",
                "estado_carrera": "Emergente (apertura >=2020), Discontinuada (sin observación 2025) o Activa.",
            },
        }
        RUTA_DICCIONARIO.write_text(json.dumps(diccionario, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Dataset definitivo: {destino}\nDiccionario: {RUTA_DICCIONARIO}")
        return destino
    except Exception as exc:
        print(f"Error al exportar dataset/metadatos: {exc}")
        raise


def generar_kpis(ruta: Path = RUTA_FINAL) -> dict[str, pd.DataFrame]:
    """Ejecuta consultas DuckDB y devuelve los tres DataFrames ejecutivos."""
    try:
        con = duckdb.connect(database=":memory:")
        p = str(ruta.resolve()).replace("'", "''")
        con.execute(f"CREATE VIEW base AS SELECT * FROM read_parquet('{p}')")
        consultas = {
            "top_crecimiento": """
                WITH x AS (SELECT codigo_unico, nomb_carrera, area_conocimiento,
                    SUM(CASE WHEN cat_periodo=2007 THEN nuevos_ingresados_definitivo ELSE 0 END) y0,
                    SUM(CASE WHEN cat_periodo=2025 THEN nuevos_ingresados_definitivo ELSE 0 END) y1
                    FROM base GROUP BY ALL)
                SELECT *, 100.0*(y1-y0)/NULLIF(y0,0) crecimiento_pct FROM x
                WHERE y0>0 AND y1 IS NOT NULL ORDER BY crecimiento_pct DESC LIMIT 15
            """,
            "brecha_aranceles": """
                SELECT cat_periodo,
                    CASE WHEN lower(coalesce(tipo_inst_2,'')) LIKE '%public%' THEN 'Pública' ELSE 'Privada/otra' END tipo_institucion,
                    AVG(valor_arancel_real) arancel_real_promedio,
                    AVG(valor_arancel_definitivo) arancel_nominal_promedio
                FROM base GROUP BY 1,2 ORDER BY 1,2
            """,
            "retencion_area": """
                WITH programa AS (
                    SELECT codigo_unico, COALESCE(area_carrera_generica, area_conocimiento, 'Sin área') area,
                        MIN(cat_periodo) apertura, MAX(cat_periodo) ultimo,
                        COUNT(DISTINCT cat_periodo) anios,
                        COUNT(DISTINCT cat_periodo) FILTER (WHERE nuevos_ingresados_definitivo>0) anios_con_ingreso
                    FROM base GROUP BY 1,2)
                SELECT area, COUNT(*) programas,
                    AVG(anios_con_ingreso / NULLIF(ultimo-apertura+1,0)) tasa_retencion_observada,
                    AVG(ultimo-apertura+1) durabilidad_anios_promedio
                FROM programa GROUP BY 1 ORDER BY programas DESC
            """,
        }
        resultados = {nombre: con.execute(sql).df() for nombre, sql in consultas.items()}
        for nombre, frame in resultados.items():
            print(f"\nKPI {nombre}:\n{frame.to_string(index=False)}")
        con.close()
        return resultados
    except Exception as exc:
        print(f"Error al generar KPIs DuckDB: {exc}")
        raise


def generar_tablero(df: pd.DataFrame, destino: Path = RUTA_TABLERO) -> Path:
    """Guarda tablero de cinco paneles con las columnas disponibles."""
    try:
        sns.set_theme(style="whitegrid")
        fig, axes = plt.subplots(2, 3, figsize=(19, 11))
        a = axes.flat
        area = "area_conocimiento" if "area_conocimiento" in df else "area_carrera_generica"
        serie = df.groupby(["cat_periodo", area], dropna=False)["nuevos_ingresados_definitivo"].sum(min_count=1).reset_index()
        top_areas = serie.groupby(area)["nuevos_ingresados_definitivo"].sum().nlargest(8).index
        sns.lineplot(data=serie[serie[area].isin(top_areas)], x="cat_periodo", y="nuevos_ingresados_definitivo", hue=area, ax=a[0])
        a[0].set_title("Primer ingreso por área")
        sns.boxplot(data=df, x="dur_total_carr_definitiva", ax=a[1], color="#6baed6")
        a[1].set_title("Duración saneada (semestres)")
        if df["valor_arancel_real"].notna().any():
            sns.lineplot(data=df.groupby("cat_periodo", as_index=False)["valor_arancel_real"].median(), x="cat_periodo", y="valor_arancel_real", ax=a[2])
            a[2].set_title("Mediana arancel real")
        else:
            a[2].text(.5, .5, "IPC no disponible: cargar ipc_anual.csv", ha="center", va="center")
            a[2].set_title("Arancel real")
        if "region_sede" in df:
            tmp = df.groupby(["region_sede", "cat_periodo"], dropna=False)["codigo_unico"].nunique().unstack(fill_value=0)
            if not tmp.empty:
                sns.heatmap(tmp, cmap="YlGnBu", ax=a[3], cbar_kws={"label": "Programas observados"})
            a[3].set_title("Programas por región y año")
        a[4].bar(["Activa", "Discontinuada", "Emergente"], df.drop_duplicates("codigo_unico")["estado_carrera"].value_counts().reindex(["Activa", "Discontinuada", "Emergente"], fill_value=0))
        a[4].set_title("Estado del ciclo de vida")
        a[5].axis("off")
        fig.suptitle("Tendencias de matrícula de Educación Superior, Chile 2007–2025", fontsize=16)
        fig.tight_layout()
        destino.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(destino, dpi=220, bbox_inches="tight")
        plt.close(fig)
        print(f"Tablero guardado: {destino}")
        return destino
    except Exception as exc:
        print(f"Error al generar tablero: {exc}")
        raise


def ejecutar_pipeline() -> pd.DataFrame:
    """Corre Bloques 9-13 usando la salida provisional existente."""
    if not RUTA_ENTRADA.is_file():
        raise FileNotFoundError(f"No se encontró la base provisional: {RUTA_ENTRADA}")
    try:
        print(f"Leyendo {RUTA_ENTRADA.name}...")
        origen = pd.read_parquet(RUTA_ENTRADA)
        ipc = pd.read_csv(RUTA_IPC) if RUTA_IPC.is_file() else None
        limpio = sanear_base_historica(origen, ipc=ipc)
        armonizado = armonizar_programas(limpio)
        exportar_dataset(armonizado)
        generar_kpis(RUTA_FINAL)
        generar_tablero(armonizado)
        del origen, limpio
        gc.collect()
        return armonizado
    except Exception as exc:
        print(f"Pipeline final detenido: {exc}")
        raise


if __name__ == "__main__":
    df_historico_definitivo = ejecutar_pipeline()
