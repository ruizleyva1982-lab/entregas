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

LIMA_TZ = pytz.timezone("America/Lima")

COLS_MOSTRAR = [
    "Número de documento",
    "Número de artículo",
    "Descripción del artículo",
    "Fecha de vencimiento",
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
def cargar_datos(_cache_key):
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    raw = ws.get_all_values()
    if raw:
        headers = raw[0]
        raw = [dict(zip(headers, row)) for row in raw[1:]]
    else:
        raw = []
    df = pd.DataFrame(raw)
    if df.empty:
        return df, datetime.now(LIMA_TZ)
    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = df["Fecha de vencimiento"].apply(parse_fecha_segura)
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce"
            )
    for col in ["De código de almacén", "Código de almacén"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    return df, datetime.now(LIMA_TZ)


# ─────────────────────────────────────────────
# ESTADO DE SESIÓN
# ─────────────────────────────────────────────
if "cache_key" not in st.session_state:
    st.session_state.cache_key = 0
if "ultima_actualizacion" not in st.session_state:
    st.session_state.ultima_actualizacion = None


# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
col_titulo, col_boton = st.columns([5, 1])
with col_titulo:
    st.title("📦 Control de Entregas")
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
# FILTROS EN PÁGINA (reemplaza sidebar)
# ─────────────────────────────────────────────
with st.container():
    # Fila 1: almacenes + estado
    c1, c2, c3 = st.columns([2, 2, 2])

    with c1:
        almacenes_origen = sorted(df["De código de almacén"].dropna().unique().tolist(), key=str)
        almacen_de = st.selectbox("🏭 De almacén (origen)", ["Todos"] + almacenes_origen)

    with c2:
        df_filtrado_origen = df if almacen_de == "Todos" else df[df["De código de almacén"] == almacen_de]
        almacenes_destino = sorted(df_filtrado_origen["Código de almacén"].dropna().unique().tolist(), key=str)
        almacen_a = st.selectbox("📍 A almacén (destino)", ["Todos"] + almacenes_destino)

    with c3:
        if "EstadoTransferencia" in df.columns:
            estados = ["Todos"] + sorted(df["EstadoTransferencia"].dropna().unique().tolist(), key=str)
            estado_sel = st.selectbox("📋 Estado de transferencia", estados)
        else:
            estado_sel = "Todos"

    # Fila 2: búsqueda + fechas
    c4, c5, c6 = st.columns([1.5, 2, 2])

    with c4:
        busqueda_tipo = st.radio(
            "🔍 Buscar por",
            ["N° Artículo", "Descripción"],
            horizontal=True,
        )

    with c5:
        busqueda_texto = st.text_input("Texto a buscar", placeholder="Ej: P1600254 o NARANJA")

    with c6:
        fechas_validas = df["Fecha de vencimiento"].dropna()
        if not fechas_validas.empty:
            fecha_min = fechas_validas.min().date()
            fecha_max = fechas_validas.max().date()
            rango_fechas = st.date_input(
                "📅 Rango de fechas (Vencimiento)",
                value=(fecha_min, fecha_max),
                min_value=fecha_min,
                max_value=fecha_max,
                format="DD/MM/YYYY",
            )
        else:
            rango_fechas = None

st.divider()


# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_vis = df.copy()

if almacen_de != "Todos":
    df_vis = df_vis[df_vis["De código de almacén"] == almacen_de]

if almacen_a != "Todos":
    df_vis = df_vis[df_vis["Código de almacén"] == almacen_a]

if busqueda_texto.strip():
    txt = busqueda_texto.strip().upper()
    if busqueda_tipo == "N° Artículo":
        df_vis = df_vis[df_vis["Número de artículo"].astype(str).str.upper().str.contains(txt, na=False)]
    else:
        df_vis = df_vis[df_vis["Descripción del artículo"].astype(str).str.upper().str.contains(txt, na=False)]

if rango_fechas and len(rango_fechas) == 2:
    f_ini = pd.Timestamp(rango_fechas[0])
    f_fin = pd.Timestamp(rango_fechas[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    df_vis = df_vis[
        (df_vis["Fecha de vencimiento"] >= f_ini) &
        (df_vis["Fecha de vencimiento"] <= f_fin)
    ]

if estado_sel != "Todos" and "EstadoTransferencia" in df_vis.columns:
    df_vis = df_vis[df_vis["EstadoTransferencia"] == estado_sel]


# ─────────────────────────────────────────────
# TABLA DETALLE
# ─────────────────────────────────────────────
st.subheader(f"📋 Detalle de movimientos — {len(df_vis):,} registros")

cols_existentes = [c for c in COLS_MOSTRAR if c in df_vis.columns]
df_tabla = df_vis[cols_existentes].copy()

if "Fecha de vencimiento" in df_tabla.columns:
    df_tabla["Fecha de vencimiento"] = df_tabla["Fecha de vencimiento"].apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
    )

for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
    if col in df_tabla.columns:
        df_tabla[col] = df_tabla[col].round(3)

df_tabla = df_tabla.rename(columns={
    "Número de artículo": "N° Artículo",
    "Descripción del artículo": "Descripción",
    "Fecha de vencimiento": "Fecha Vcto.",
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
    if "Fecha de vencimiento" in csv.columns:
        csv["Fecha de vencimiento"] = csv["Fecha de vencimiento"].apply(
            lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
        )
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
