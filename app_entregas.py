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

# Scopes de Google Sheets / Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ID de tu Google Sheet (la parte de la URL entre /d/ y /edit)
# Ejemplo: https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit
SPREADSHEET_ID = "1OQm27gEcI3-YylG03BpzbZewRqlYmkZydIhRklY7x1c"   # <-- CAMBIAR
SHEET_NAME = "Hoja1"                          # <-- CAMBIAR si la hoja tiene otro nombre

# Zona horaria de Lima
LIMA_TZ = pytz.timezone("America/Lima")

# Columnas que necesitamos mostrar en la tabla
COLS_MOSTRAR = [
    "Número de artículo",
    "Descripción del artículo",
    "Fecha de vencimiento",
    "Cantidad",
    "CantidadAtendida",
    "CantidadPendiente",
]

# Nombres de almacenes (puedes ampliar este dict)
NOMBRES_ALMACEN = {
    "10": "10",
    "11": "11",
    "14": "14",
    "55": "55",
    "72": "72",
    "T30": "T30",
}


# ─────────────────────────────────────────────
# FUNCIONES
# ─────────────────────────────────────────────

def get_gspread_client():
    """Crea cliente gspread desde st.secrets."""
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def parse_fecha_segura(valor):
    """
    Convierte un valor de celda a fecha de forma segura.
    Evita el bug DD/MM ↔ MM/DD: siempre interpreta el formato
    de Google Sheets como YYYY-MM-DD o como número serial de Excel.
    Retorna pd.NaT si no puede parsear.
    """
    if pd.isna(valor) or valor == "" or valor is None:
        return pd.NaT

    # Ya es datetime o date
    if isinstance(valor, (datetime,)):
        return pd.Timestamp(valor)

    # Número serial de Excel (Google Sheets a veces lo devuelve así)
    if isinstance(valor, (int, float)):
        try:
            # Excel serial: días desde 1900-01-01 (con bug del año bisiesto 1900)
            return pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(valor))
        except Exception:
            return pd.NaT

    # String
    s = str(valor).strip()
    if not s:
        return pd.NaT

    # Intentar parseo explícito en orden de prioridad
    formatos = [
        "%Y-%m-%d",          # ISO → lo más seguro
        "%d/%m/%Y",          # formato peruano DD/MM/YYYY
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",          # solo si los anteriores fallan
    ]
    for fmt in formatos:
        try:
            return pd.Timestamp(datetime.strptime(s, fmt))
        except ValueError:
            continue

    # Último recurso: pandas (puede confundirse con DD/MM vs MM/DD)
    try:
        return pd.Timestamp(s)
    except Exception:
        return pd.NaT


@st.cache_data(ttl=0, show_spinner=False)
def cargar_datos(_cache_key):
    """
    Descarga los datos del Google Sheet.
    _cache_key cambia cada vez que el usuario presiona "Recargar"
    para forzar la recarga.
    """
    client = get_gspread_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)

    raw = ws.get_all_records(
    expected_headers=[],
    value_render_option="UNFORMATTED_VALUE",
    )

    df = pd.DataFrame(raw)

    if df.empty:
        return df, datetime.now(LIMA_TZ)

    # ── Parseo de fecha de vencimiento ────────────────────────────────
    if "Fecha de vencimiento" in df.columns:
        df["Fecha de vencimiento"] = df["Fecha de vencimiento"].apply(parse_fecha_segura)

    # ── Columnas numéricas ─────────────────────────────────────────────
    for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Almacenes como string para evitar mezcla int/str ──────────────
    for col in ["De código de almacén", "Código de almacén"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    ultima_actualizacion = datetime.now(LIMA_TZ)
    return df, ultima_actualizacion


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
    st.title("📦 Control de Entregas — María Almenara")

with col_boton:
    st.write("")  # espaciado vertical
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

# Mostrar última actualización
if st.session_state.ultima_actualizacion:
    ts = st.session_state.ultima_actualizacion.strftime("%d/%m/%Y %H:%M:%S")
    st.caption(f"🕒 Última actualización: **{ts}** (hora Lima)")

st.divider()

# ─────────────────────────────────────────────
# FILTROS PRINCIPALES (sidebar)
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Filtros")

    # Almacenes origen
    almacenes_origen = sorted(df["De código de almacén"].dropna().unique().tolist())
    almacen_de = st.selectbox(
        "De almacén (origen)",
        options=["Todos"] + almacenes_origen,
        index=0,
    )

    # Almacenes destino (dinámico según origen)
    df_filtrado_origen = df if almacen_de == "Todos" else df[df["De código de almacén"] == almacen_de]
    almacenes_destino = sorted(df_filtrado_origen["Código de almacén"].dropna().unique().tolist())
    almacen_a = st.selectbox(
        "A almacén (destino)",
        options=["Todos"] + almacenes_destino,
        index=0,
    )

    st.divider()

    # Filtro por artículo
    st.subheader("🔍 Buscar artículo")
    busqueda_tipo = st.radio(
        "Buscar por",
        ["Número de artículo", "Descripción del artículo"],
        horizontal=True,
    )
    busqueda_texto = st.text_input("Ingresa texto a buscar", placeholder="Ej: P1600254 o NARANJA")

    st.divider()

    # Filtro por rango de fechas
    st.subheader("📅 Rango de fechas (Vencimiento)")
    fechas_validas = df["Fecha de vencimiento"].dropna()
    if not fechas_validas.empty:
        fecha_min = fechas_validas.min().date()
        fecha_max = fechas_validas.max().date()
        rango_fechas = st.date_input(
            "Desde / Hasta",
            value=(fecha_min, fecha_max),
            min_value=fecha_min,
            max_value=fecha_max,
            format="DD/MM/YYYY",
        )
    else:
        rango_fechas = None

    st.divider()

    # Filtro por estado de transferencia
    if "EstadoTransferencia" in df.columns:
        estados = ["Todos"] + sorted(df["EstadoTransferencia"].dropna().unique().tolist())
        estado_sel = st.selectbox("Estado de transferencia", estados)
    else:
        estado_sel = "Todos"


# ─────────────────────────────────────────────
# APLICAR FILTROS
# ─────────────────────────────────────────────
df_vis = df.copy()

# Almacén origen
if almacen_de != "Todos":
    df_vis = df_vis[df_vis["De código de almacén"] == almacen_de]

# Almacén destino
if almacen_a != "Todos":
    df_vis = df_vis[df_vis["Código de almacén"] == almacen_a]

# Búsqueda por artículo
if busqueda_texto.strip():
    txt = busqueda_texto.strip().upper()
    if busqueda_tipo == "Número de artículo":
        df_vis = df_vis[df_vis["Número de artículo"].astype(str).str.upper().str.contains(txt, na=False)]
    else:
        df_vis = df_vis[df_vis["Descripción del artículo"].astype(str).str.upper().str.contains(txt, na=False)]

# Rango de fechas
if rango_fechas and len(rango_fechas) == 2:
    f_ini = pd.Timestamp(rango_fechas[0])
    f_fin = pd.Timestamp(rango_fechas[1]) + pd.Timedelta(hours=23, minutes=59, seconds=59)
    df_vis = df_vis[
        (df_vis["Fecha de vencimiento"] >= f_ini) &
        (df_vis["Fecha de vencimiento"] <= f_fin)
    ]

# Estado de transferencia
if estado_sel != "Todos" and "EstadoTransferencia" in df_vis.columns:
    df_vis = df_vis[df_vis["EstadoTransferencia"] == estado_sel]


# ─────────────────────────────────────────────
# MÉTRICAS RESUMEN
# ─────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total registros", f"{len(df_vis):,}")
m2.metric("Cantidad total", f"{df_vis['Cantidad'].sum():,.3f}")
m3.metric("Cant. Atendida", f"{df_vis['CantidadAtendida'].sum():,.3f}")
m4.metric("Cant. Pendiente", f"{df_vis['CantidadPendiente'].sum():,.3f}")

st.divider()

# ─────────────────────────────────────────────
# TABLA DETALLE
# ─────────────────────────────────────────────
st.subheader("📋 Detalle de movimientos")

# Preparar tabla de visualización
cols_existentes = [c for c in COLS_MOSTRAR if c in df_vis.columns]
df_tabla = df_vis[cols_existentes].copy()

# Formatear fecha de vencimiento para display DD/MM/YYYY
if "Fecha de vencimiento" in df_tabla.columns:
    df_tabla["Fecha de vencimiento"] = df_tabla["Fecha de vencimiento"].apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
    )

# Redondear decimales
for col in ["Cantidad", "CantidadAtendida", "CantidadPendiente"]:
    if col in df_tabla.columns:
        df_tabla[col] = df_tabla[col].round(3)

# Renombrar columnas para display
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
            "Cantidad":   st.column_config.NumberColumn("Cantidad",   format="%.3f"),
            "Atendida":   st.column_config.NumberColumn("Atendida",   format="%.3f"),
            "Pendiente":  st.column_config.NumberColumn("Pendiente",  format="%.3f"),
        },
    )

    # Botón de descarga
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
# TABLA AGRUPADA POR ARTÍCULO
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
