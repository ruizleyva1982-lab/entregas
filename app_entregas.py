import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Control de Entregas",
    page_icon="📦",
    layout="wide",
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

SPREADSHEET_ID = "1OQm27gEcI3-YylG03BpzbZewRqlYmkZydIhRklY7x1c"
SHEET_NAME = "Hoja1"
SHEET_NAME2 = "Hoja2"

LIMA_TZ = pytz.timezone("America/Lima")

COLS_MOSTRAR = [
    "Número de documento",
    "Número de artículo",
    "Descripción del artículo",
    "Cantidad",
    "CantidadAtendida",
    "CantidadPendiente",
]


# ─────────────────────────────────────────────
# FUNCIONES
# ─────────────────────────────────────────────

def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def parse_fecha_segura(valor):
    if pd.isna(valor) or valor == "" or valor is None:
        return pd.NaT
    if isinstance(valor, datetime):
        return pd.Timestamp(valor)
    if isinstance(valor, (int, float)):
        try:
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(valor))
        except Exception:
            return pd.NaT
    s = str(valor).strip()
    if not s:
        return pd.NaT
    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"]
    for fmt in formatos:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt))
        except ValueError:
            continue
    try:
        return pd.Timestamp(s)
    except Exception:
        return pd.NaT


@st.cache_data(ttl=0, show_spinner=False)
def detectar_st_relacionadas(df):
    """
    Detecta ST (Solicitudes de Transferencia) que aparentan no estar
    atendidas pero que tienen una "ST hermana" del mismo día, mismo
    artículo, mismas bodegas y misma cantidad que SÍ fue atendida.

    Esto ocurre cuando el almacén origen cierra una ST sin transferir
    (por falta de stock físico) y luego se crea una nueva ST que sí
    se atiende. La primera queda con CantidadPendiente > 0 pero en
    realidad la necesidad ya fue cubierta por la segunda.

    Versión vectorizada con merge (rápida incluso con ~200k filas).
    """
    cols_necesarias = [
        "Número de documento", "Número de artículo", "De código de almacén",
        "Código de almacén", "Cantidad", "CantidadAtendida", "CantidadPendiente",
        "Fecha de contabilización",
    ]
    if not all(c in df.columns for c in cols_necesarias):
        return pd.DataFrame()

    base = df[cols_necesarias].copy()
    base = base.dropna(subset=["Fecha de contabilización"])
    base["fecha_dia"] = base["Fecha de contabilización"].dt.date
    base["cantidad_r"] = base["Cantidad"].round(3)

    claves = ["Número de artículo", "De código de almacén", "Código de almacén", "cantidad_r", "fecha_dia"]

    no_atendidas = base[base["CantidadPendiente"] > 0]
    atendidas = base[base["CantidadAtendida"] > 0]

    if no_atendidas.empty or atendidas.empty:
        return pd.DataFrame()

    merged = no_atendidas.merge(
        atendidas,
        on=claves,
        suffixes=("_pend", "_atend"),
    )

    # Quitar auto-match (la misma ST contra sí misma)
    merged = merged[merged["Número de documento_pend"] != merged["Número de documento_atend"]]

    if merged.empty:
        return pd.DataFrame()

    resultado = merged.rename(columns={
        "Número de artículo": "Número de artículo",
        "Número de documento_pend": "ST sin atender",
        "CantidadPendiente_pend": "Cant. pendiente (ST sin atender)",
        "Número de documento_atend": "ST que sí se atendió",
        "CantidadAtendida_atend": "Cant. atendida (ST hermana)",
        "De código de almacén": "De almacén",
        "Código de almacén": "A almacén",
        "fecha_dia": "Fecha",
    })[[
        "Número de artículo", "ST sin atender", "Cant. pendiente (ST sin atender)",
        "ST que sí se atendió", "Cant. atendida (ST hermana)", "De almacén", "A almacén", "Fecha",
    ]]

    return resultado.drop_duplicates(subset=["ST sin atender", "ST que sí se atendió"])




@st.cache_data(ttl=0, show_spinner=False)
def cargar_datos(_cache_key):
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)

    # ── Hoja1: datos principales ──
    ws = sh.worksheet(SHEET_NAME)
    raw = ws.get_all_values()
    if raw:
        headers = raw[0]
        df = pd.DataFrame(raw[1:], columns=headers)
        df = df.loc[:, ~df.columns.duplicated(keep='first')]
    else:
        df = pd.DataFrame()
    if df.empty:
        return df, datetime.now(LIMA_TZ)

    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = df["Fecha de vencimiento"].apply(parse_fecha_segura)
    if "Fecha de contabilización" in df.columns:
        df["Fecha de contabilización"] = df["Fecha de contabilización"].apply(parse_fecha_segura)
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            s = df[col].astype(str).str.strip()
            tiene_punto = s.str.contains(r'\.', regex=True)
            s = s.where(tiene_punto, s.str.replace(",", ".", regex=False))
            s = s.where(~tiene_punto, s.str.replace(",", "", regex=False))
            df[col] = pd.to_numeric(s, errors="coerce")
    for col in ["De código de almacén", "Código de almacén"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # Pre-calcular columnas en mayúsculas para búsquedas rápidas (evita
    # recalcular .str.upper() en cada filtro del usuario)
    if "Número de artículo" in df.columns:
        df["_busq_articulo"] = df["Número de artículo"].astype(str).str.upper()
    if "Descripción del artículo" in df.columns:
        df["_busq_descripcion"] = df["Descripción del artículo"].astype(str).str.upper()

    # ── Hoja2: líneas de producción ──
    try:
        ws2 = sh.worksheet(SHEET_NAME2)
        raw2 = ws2.get_all_values()
        if raw2:
            headers2 = raw2[0]
            df2 = pd.DataFrame([dict(zip(headers2, r)) for r in raw2[1:]])
            df2 = df2[["Número de artículo", "Linea de Producción"]].drop_duplicates(subset=["Número de artículo"])
            df2 = df2[df2["Número de artículo"].str.strip() != ""]
            df = df.merge(df2, on="Número de artículo", how="left")
    except Exception:
        df["Linea de Producción"] = ""

    return df, datetime.now(LIMA_TZ)


# ─────────────────────────────────────────────
# ESTADO DE SESIÓN
# ─────────────────────────────────────────────
if "cache_key" not in st.session_state:
    st.session_state.cache_key = 0
if "ultima_actualizacion" not in st.session_state:
    st.session_state.ultima_actualizacion = None

# Filtros aplicados (se actualizan solo al presionar "Aplicar filtros")
if "filtros_aplicados" not in st.session_state:
    st.session_state.filtros_aplicados = {
        "almacen_de": "Todos",
        "almacen_a": "Todos",
        "grupo_sel": "Todos",
        "busqueda_tipo": "Número de artículo",
        "busqueda_texto": "",
        "rango_fechas": None,
    }


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
LOGO_B64 = "/9j/4AAQSkZJRgABAQEAYABgAAD/4QLmRXhpZgAATU0AKgAAAAgABAE7AAIAAAAJAAABSodpAAQAAAABAAABVJydAAEAAAASAAACzOocAAcAAAEMAAAAPgAAAAAc6gAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAU3RlZmZhbm8AAAAFkAMAAgAAABQAAAKikAQAAgAAABQAAAK2kpEAAgAAAAM2NQAAkpIAAgAAAAM2NQAA6hwABwAAAQwAAAGWAAAAABzqAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAyMDI2OjA2OjA0IDIzOjU4OjM5ADIwMjY6MDY6MDQgMjM6NTg6MzkAAABTAHQAZQBmAGYAYQBuAG8AAAD/4QQbaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49J++7vycgaWQ9J1c1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCc/Pg0KPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyI+PHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj48cmRmOkRlc2NyaXB0aW9uIHJkZjphYm91dD0idXVpZDpmYWY1YmRkNS1iYTNkLTExZGEtYWQzMS1kMzNkNzUxODJmMWIiIHhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIvPjxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSJ1dWlkOmZhZjViZGQ1LWJhM2QtMTFkYS1hZDMxLWQzM2Q3NTE4MmYxYiIgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIj48eG1wOkNyZWF0ZURhdGU+MjAyNi0wNi0wNFQyMzo1ODozOS42NDY8L3htcDpDcmVhdGVEYXRlPjwvcmRmOkRlc2NyaXB0aW9uPjxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSJ1dWlkOmZhZjViZGQ1LWJhM2QtMTFkYS1hZDMxLWQzM2Q3NTE4MmYxYiIgeG1sbnM6ZGM9Imh0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvIj48ZGM6Y3JlYXRvcj48cmRmOlNlcSB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiPjxyZGY6bGk+U3RlZmZhbm88L3JkZjpsaT48L3JkZjpTZXE+DQoJCQk8L2RjOmNyZWF0b3I+PC9yZGY6RGVzY3JpcHRpb24+PC9yZGY6UkRGPjwveDp4bXBtZXRhPg0KICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIDw/eHBhY2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"

col_logo, col_titulo, col_boton = st.columns([0.7, 5, 1.2])
with col_logo:
    st.markdown(
        f'''<img src="data:image/jpeg;base64,{LOGO_B64}" style="width:70px;margin-top:8px;">''',
        unsafe_allow_html=True,
    )
with col_titulo:
    st.title("Control de Entregas")
with col_boton:
    st.write("")
    if st.button("🔄 Recargar datos", use_container_width=True, type="primary"):
        st.session_state.cache_key += 1
        cargar_datos.clear()


# ─────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────
with st.spinner("Cargando datos desde Google Sheets…"):
    try:
        df, ultima_actualizacion = cargar_datos(st.session_state.cache_key)
        st.session_state.ultima_actualizacion = ultima_actualizacion
    except Exception as e:
        st.error(f"❌ Error al conectar con Google Sheets: {e}")
        st.stop()

if df.empty:
    st.warning("La hoja está vacía.")
    st.stop()

if st.session_state.ultima_actualizacion:
    ts = st.session_state.ultima_actualizacion.strftime("%d/%m/%Y %H:%M:%S")
    st.caption(f"🕒 Última actualización: **{ts}** (hora Lima)")

st.divider()


# ─────────────────────────────────────────────
# FILTROS EN PÁGINA — DENTRO DE UN FORM
# (no se aplica nada hasta presionar "Aplicar filtros")
# ─────────────────────────────────────────────
with st.form("filtros_form"):
    # Fila 1: almacenes + línea de producción
    c1, c2, c3 = st.columns([2, 2, 2])

    with c1:
        almacenes_origen = sorted(df["De código de almacén"].dropna().unique().tolist(), key=str)
        almacen_de_input = st.selectbox(
            "🏭 De almacén (origen)",
            ["Todos"] + almacenes_origen,
            index=(["Todos"] + almacenes_origen).index(st.session_state.filtros_aplicados["almacen_de"])
                  if st.session_state.filtros_aplicados["almacen_de"] in (["Todos"] + almacenes_origen) else 0,
        )

    with c2:
        # Nota: el listado de destino se calcula sobre TODO el df (no sobre el filtro de origen
        # todavía no aplicado), para evitar que cambie antes de presionar el botón.
        almacenes_destino = sorted(df["Código de almacén"].dropna().unique().tolist(), key=str)
        almacen_a_input = st.selectbox(
            "📍 A almacén (destino)",
            ["Todos"] + almacenes_destino,
            index=(["Todos"] + almacenes_destino).index(st.session_state.filtros_aplicados["almacen_a"])
                  if st.session_state.filtros_aplicados["almacen_a"] in (["Todos"] + almacenes_destino) else 0,
        )

    with c3:
        if "Linea de Producción" in df.columns:
            grupos = ["Todos"] + sorted([x for x in df["Linea de Producción"].dropna().unique().tolist() if str(x).strip()], key=str)
            grupo_sel_input = st.selectbox(
                "🏭 Línea de producción",
                grupos,
                index=grupos.index(st.session_state.filtros_aplicados["grupo_sel"])
                      if st.session_state.filtros_aplicados["grupo_sel"] in grupos else 0,
            )
        else:
            grupo_sel_input = "Todos"

    # Fila 2: búsqueda + fechas
    c4, c5, c6 = st.columns([1.5, 2, 2])

    with c4:
        opciones_busqueda = ["Número de artículo", "Descripción del artículo"]
        busqueda_tipo_input = st.radio(
            "🔍 Buscar por",
            opciones_busqueda,
            horizontal=True,
            index=opciones_busqueda.index(st.session_state.filtros_aplicados["busqueda_tipo"]),
        )

    with c5:
        busqueda_texto_input = st.text_input(
            "Texto a buscar",
            value=st.session_state.filtros_aplicados["busqueda_texto"],
            placeholder="Ej: P1600254 o NARANJA",
        )

    with c6:
        fechas_validas = df["Fecha de vencimiento"].dropna()
        if not fechas_validas.empty:
            fecha_min = fechas_validas.min().date()
            fecha_max = fechas_validas.max().date()
            valor_default = st.session_state.filtros_aplicados["rango_fechas"] or (fecha_min, fecha_max)
            rango_fechas_input = st.date_input(
                "📅 Rango de fechas (Vencimiento)",
                value=valor_default,
                min_value=fecha_min,
                max_value=fecha_max,
                format="DD/MM/YYYY",
            )
        else:
            rango_fechas_input = None

    aplicar = st.form_submit_button("✅ Aplicar filtros", type="primary", use_container_width=False)

    if aplicar:
        st.session_state.filtros_aplicados = {
            "almacen_de": almacen_de_input,
            "almacen_a": almacen_a_input,
            "grupo_sel": grupo_sel_input,
            "busqueda_tipo": busqueda_tipo_input,
            "busqueda_texto": busqueda_texto_input,
            "rango_fechas": rango_fechas_input,
        }

st.divider()


# ─────────────────────────────────────────────
# APLICAR FILTROS (usa lo guardado en session_state, NO los widgets en vivo)
# ─────────────────────────────────────────────
filtros = st.session_state.filtros_aplicados

# Construir una sola máscara booleana vectorizada en lugar de
# ir recortando el DataFrame paso a paso (mucho más rápido con
# datasets grandes, ~200k filas).
mask = pd.Series(True, index=df.index)

if filtros["almacen_de"] != "Todos":
    mask &= (df["De código de almacén"] == filtros["almacen_de"])

if filtros["almacen_a"] != "Todos":
    mask &= (df["Código de almacén"] == filtros["almacen_a"])

if filtros["busqueda_texto"].strip():
    txt = filtros["busqueda_texto"].strip().upper()
    col_busq = "_busq_articulo" if filtros["busqueda_tipo"] == "Número de artículo" else "_busq_descripcion"
    mask &= df[col_busq].str.contains(txt, na=False, regex=False)

if filtros["rango_fechas"] and len(filtros["rango_fechas"]) == 2:
    f_ini = pd.Timestamp(filtros["rango_fechas"][0])
    f_fin = pd.Timestamp(filtros["rango_fechas"][1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    mask &= (df["Fecha de vencimiento"] >= f_ini) & (df["Fecha de vencimiento"] <= f_fin)

if filtros["grupo_sel"] != "Todos" and "Linea de Producción" in df.columns:
    mask &= (df["Linea de Producción"] == filtros["grupo_sel"])

df_vis = df[mask]


# ─────────────────────────────────────────────
# TABLA DETALLE
# ─────────────────────────────────────────────
st.subheader(f"📋 Detalle de movimientos — {len(df_vis):,} registros")

cols_existentes = [c for c in COLS_MOSTRAR if c in df_vis.columns]
df_tabla = df_vis[cols_existentes].copy()

for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
    if col in df_tabla.columns:
        df_tabla[col] = df_tabla[col].round(3)

df_tabla = df_tabla.rename(columns={
    "Número de documento": "N° Documento",
    "Número de artículo": "N° Artículo",
    "Descripción del artículo": "Descripción",
    "CantidadAtendida": "Atendida",
    "CantidadPendiente": "Pendiente",
})

if df_tabla.empty:
    st.info("No hay registros con los filtros seleccionados.")
else:
    st.dataframe(
        df_tabla,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Cantidad":  st.column_config.NumberColumn("Cantidad", format="%.3f"),
            "Atendida":  st.column_config.NumberColumn("Atendida", format="%.3f"),
            "Pendiente": st.column_config.NumberColumn("Pendiente", format="%.3f"),
        },
    )

    csv = df_vis[cols_existentes].copy()
    csv_bytes = csv.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="⬇️ Descargar CSV",
        data=csv_bytes,
        file_name=f"entregas_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


# ─────────────────────────────────────────────
# TABLA AGRUPADA
# ─────────────────────────────────────────────
with st.expander("📊 Resumen agrupado por artículo"):
    if not df_vis.empty:
        grp = (
            df_vis.groupby(["Número de artículo", "Descripción del artículo"], as_index=False)
            .agg(
                Cantidad=("Cantidad", "sum"),
                Atendida=("CantidadAtendida", "sum"),
                Pendiente=("CantidadPendiente", "sum"),
                Registros=("Cantidad", "count"),
            )
            .sort_values("Pendiente", ascending=False)
        )
        for c in ["Cantidad", "Atendida", "Pendiente"]:
            grp[c] = grp[c].round(3)
        st.dataframe(
            grp,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cantidad":  st.column_config.NumberColumn(format="%.3f"),
                "Atendida":  st.column_config.NumberColumn(format="%.3f"),
                "Pendiente": st.column_config.NumberColumn(format="%.3f"),
            },
        )

# ─────────────────────────────────────────────
# ALERTA: ST POSIBLEMENTE DUPLICADAS / YA CUBIERTAS
# ─────────────────────────────────────────────
with st.expander("⚠️ ST posiblemente duplicadas o ya cubiertas"):
    st.caption(
        "Detecta ST con cantidad pendiente que tienen otra ST del mismo día, "
        "mismo artículo y mismos almacenes que sí fue atendida. Esto suele pasar "
        "cuando una ST se cierra sin transferencia por falta de stock físico y "
        "luego se crea una nueva ST que sí se atiende."
    )
    alertas_df = detectar_st_relacionadas(df)

    if alertas_df.empty:
        st.info("No se detectaron ST con este patrón en los datos actuales.")
    else:
        st.warning(f"Se encontraron {len(alertas_df)} posible(s) caso(s).")
        st.dataframe(
            alertas_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cant. pendiente (ST sin atender)": st.column_config.NumberColumn(format="%.3f"),
                "Cant. atendida (ST hermana)": st.column_config.NumberColumn(format="%.3f"),
            },
        )
        st.caption(
            "⚠️ Verifica cada caso: también puede ocurrir que se haya pedido el mismo "
            "insumo en otra ST por una necesidad real distinta. La coincidencia de "
            "artículo + almacenes + cantidad + fecha es una señal, no una certeza."
        )
