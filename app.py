import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador Heredia", page_icon="🏭", layout="wide")

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, h_lj, h_v):
    fin = h_lj if dt.weekday() <= 3 else h_v
    return dt.replace(hour=fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, feriados, h_ini, h_lj, h_v):
    while True:
        if dt.weekday() >= 5 or dt.strftime("%Y-%m-%d") in feriados:
            dt = (dt + timedelta(days=1)).replace(hour=h_ini, minute=0, second=0)
            continue
        fin = h_lj if dt.weekday() <= 3 else h_v
        if dt.hour >= fin:
            dt = (dt + timedelta(days=1)).replace(hour=h_ini, minute=0, second=0)
            continue
        if dt.hour < h_ini:
            dt = dt.replace(hour=h_ini, minute=0, second=0)
        return dt

# --- INICIALIZACIÓN DE DATOS ---
if 'df_pedidos' not in st.session_state:
    st.session_state.df_pedidos = pd.DataFrame(
        [{"Orden": 1, "Código": "", "Cantidad": 0.0, "Setup": 0.0}],
        columns=["Orden", "Código", "Cantidad", "Setup"]
    )

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_ini = st.sidebar.number_input("Hora Inicio Turno", 0, 23, 7)
h_lj = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_v = st.sidebar.number_input("Salida Viernes", 0, 23, 15)
feriados_input = st.sidebar.date_input("Días Feriados", [])
feriados = [d.strftime("%Y-%m-%d") for d in feriados_input]

# --- CUERPO PRINCIPAL ---
st.title("🏭 Planificador de Producción Interactivo")

file_cat = st.file_uploader("1. Sube el Catálogo de Productos", type=["xlsx"])

if file_cat:
    # Cargar catálogo de forma segura (evitando el error de duplicados)
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    catalogo = df_cat.drop_duplicates(subset=['Código']).set_index('Código').to_dict('index')

    st.divider()
    
    # 2. Tabla de Ingreso Directo
    st.subheader("📋 Tabla de Pedidos")
    st.info("💡 Digita en las celdas, pega valores o usa el '+' al final para nuevas filas.")
    
    # Editor de datos
    edited_df = st.data_editor(
        st.session_state.df_pedidos,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Orden": st.column_config.NumberColumn("Orden", min_value=1, step=1),
            "Código": st.column_config.TextColumn("Código Material"),
            "Cantidad": st.column_config.NumberColumn("Kg", min_value=0),
            "Setup": st.column_config.NumberColumn("Setup (h)", min_value=0, step=0.5)
        },
        key="editor_principal"
    )
    st.session_state.df_pedidos = edited_df

    if st.button("🗑️ Borrar toda la tabla"):
        st.session_state.df_pedidos = pd.DataFrame(
            [{"Orden": 1, "Código": "", "Cantidad": 0.0, "Setup": 0.0}],
            columns=["Orden", "Código", "Cantidad", "Setup"]
        )
        st.rerun()

    # 3. Cálculo del Cronograma
    st.divider()
    fecha_inicio_plan = st.date_input("📅 Fecha de inicio de producción", datetime.now())

    # Validamos que haya datos para calcular
    df_para_calc = edited_df[edited_df['Código'].astype(str).str.strip() != ""]
    
    if not df_para_calc.empty:
        st.subheader("📅 Cronograma Resultante")
        
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_ini)
        plan_calculado = []

        # Ordenar por 'Orden' para respetar la prioridad del usuario
        for _, fila in df_para_calc.sort_values("Orden").iterrows():
            cod_str = str(fila['Código']).strip()
            
            if cod_str in catalogo:
                info = catalogo[cod_str]
                tasa_kgh = float(info['Tasa']) * 1000
                peso_u = float(info.get('Peso unitario', 1))
                
                # Proceso Setup
                rem_s = float(fila['Setup'])
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
                
                inicio_prod = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                
                # Proceso Producción
                rem_c = float(fila['Cantidad'])
                while rem_c > 0.001:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados, h_ini, h_lj, h_v)
                    cap_kg = ((obtener_fin_turno(tiempo_actual, h_lj, h_v) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                    prod_kg = min(rem_c, cap_kg)
                    tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
                
                plan_calculado.append({
                    "PRIORIDAD": fila['Orden'],
                    "CÓDIGO": cod_str,
                    "PRODUCTO": info['Producto'],
                    "INICIO": inicio_prod.strftime('%d/%m/%y %I:%M %p'),
                    "FIN": tiempo_actual.strftime('%d/%m/%y %I:%M %p')
                })

        if plan_calculado:
            df_final = pd.DataFrame(plan_calculado)
            st.dataframe(df_final, use_container_width=True)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, sheet_name='Plan', index=False)
            st.download_button("📥 Descargar Plan en Excel", data=output.getvalue(), file_name="Plan_Produccion.xlsx")
        else:
            st.warning("⚠️ Ingresa códigos válidos del catálogo para calcular.")

else:
    st.info("👋 Sube el archivo de catálogo para habilitar la tabla.")
