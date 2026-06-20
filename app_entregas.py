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
    page_title="Control de Entregas de Productos Terminados",
    page_icon="🍰",
    layout="wide",
)

# ─────────────────────────────────────────────
# ESTILO CORPORATIVO MARÍA ALMENARA (rojo/blanco)
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* Fondo general con textura sutil */
    .stApp {
        background:
            radial-gradient(circle at 15% 0%, rgba(196,30,40,0.05) 0%, transparent 45%),
            radial-gradient(circle at 100% 30%, rgba(196,30,40,0.04) 0%, transparent 40%),
            #FAFAF8;
    }

    /* Tipografía general */
    html, body, [class*="css"] {
        font-family: 'Trebuchet MS', 'Segoe UI', sans-serif;
    }

    /* Header corporativo con gradiente rojo */
    .ma-header {
        background: linear-gradient(120deg, #C41E28 0%, #8E1219 100%);
        border-radius: 18px;
        padding: 28px 36px;
        margin-bottom: 18px;
        box-shadow: 0 8px 24px rgba(196,30,40,0.25);
        display: flex;
        align-items: center;
        gap: 18px;
    }
    .ma-header-icon {
        font-size: 42px;
        line-height: 1;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.25));
    }
    .ma-header-text h1 {
        color: #FFFFFF !important;
        font-size: 30px;
        font-weight: 800;
        margin: 0;
        letter-spacing: 0.3px;
        text-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }
    .ma-header-text p {
        color: #FFE3E3;
        font-size: 14px;
        margin: 2px 0 0 0;
        font-weight: 500;
        letter-spacing: 0.5px;
    }

    /* Tarjeta de filtros */
    div[data-testid="stForm"] {
        background: #FFFFFF;
        border: 1px solid #F0D5D6;
        border-radius: 16px;
        padding: 22px 26px 8px 26px;
        box-shadow: 0 4px 18px rgba(0,0,0,0.05);
    }

    /* Botón primario (Aplicar filtros / Recargar) */
    button[kind="primary"] {
        background: linear-gradient(120deg, #C41E28 0%, #8E1219 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 12px rgba(196,30,40,0.3) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(196,30,40,0.4) !important;
    }

    /* Subheaders con barra roja lateral */
    h3 {
        border-left: 5px solid #C41E28;
        padding-left: 12px !important;
    }

    /* Tablas */
    div[data-testid="stDataFrame"] {
        border-radius: 14px;
        overflow: hidden;
        box-shadow: 0 4px 16px rgba(0,0,0,0.06);
        border: 1px solid #EFEFEF;
    }

    /* Expanders */
    details {
        background: #FFFFFF;
        border: 1px solid #F0D5D6 !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    }
    summary {
        font-weight: 700 !important;
        color: #8E1219 !important;
    }

    /* Caption / texto secundario */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #7A4A4C !important;
    }

    /* Divider más sutil */
    hr {
        border-color: #F0D5D6 !important;
    }
</style>
""", unsafe_allow_html=True)

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


@st.cache_data(show_spinner=False)
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




@st.cache_data(show_spinner=False)
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
col_titulo, col_boton = st.columns([5, 1.2])
with col_titulo:
    st.markdown(
        """
        <div class="ma-header">
            <div class="ma-header-icon">🍰</div>
            <div class="ma-header-text">
                <h1>Control de Entrega de Productos Terminados</h1>
                <p>MARÍA ALMENARA · GESTIÓN DE TRANSFERENCIAS ENTRE ALMACENES</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with col_boton:
    st.write("")
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

    if st.button("🔍 Buscar ST posiblemente duplicadas", key="btn_detectar_st"):
        st.session_state["alertas_df"] = detectar_st_relacionadas(df)

    alertas_df = st.session_state.get("alertas_df")

    if alertas_df is None:
        st.info("Presiona el botón para analizar las ST (puede tardar unos segundos).")
    elif alertas_df.empty:
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
