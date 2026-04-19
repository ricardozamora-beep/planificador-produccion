import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador Masivo - Heredia", page_icon="⏱️", layout="wide")

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, hora_lun_jue, hora_vie):
    hora_fin = hora_lun_jue if dt.weekday() <= 3 else hora_vie
    return dt.replace(hour=hora_fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, lista_feriados, hora_inicio_turno, hora_lun_jue, hora_vie):
    while True:
        dia_semana = dt.weekday()
        fecha_actual_str = dt.strftime("%Y-%m-%d")
        if dia_semana >= 5 or fecha_actual_str in lista_feriados:
            dt = (dt + timedelta(days=1)).replace(hour=hora_inicio_turno, minute=0, second=0)
            continue
        hora_salida = hora_lun_jue if dia_semana <= 3 else hora_vie
        if dt.hour >= hora_salida:
            dt = (dt + timedelta(days=1)).replace(hour=hora_inicio_turno, minute=0, second=0)
            continue
        if dt.hour < hora_inicio_turno:
            dt = dt.replace(hour=hora_inicio_turno, minute=0, second=0)
        return dt

# --- DIÁLOGO DE CONFIRMACIÓN ---
@st.dialog("¿Limpiar todo el plan?")
def confirmar_borrar_todo():
    st.write("Se borrarán todos los datos ingresados en la tabla.")
    if st.button("Sí, limpiar tabla"):
        st.session_state.data_editor_input = pd.DataFrame(columns=["Código", "Cantidad", "Setup"])
        st.rerun()

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_inicio = st.sidebar.number_input("Hora Inicio Turno", 0, 23, 7)
h_lun_jue = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_vie = st.sidebar.number_input("Salida Viernes", 0, 23, 15)
feriados_sel = st.sidebar.date_input("Días Feriados", value=[])
lista_feriados = [d.strftime("%Y-%m-%d") for d in feriados_sel]

# --- CUERPO PRINCIPAL ---
st.title("⏱️ Planificador de Producción Masivo")
st.markdown("Pega tus datos directamente en la tabla (Código, Cantidad y Setup).")

file_cat = st.file_uploader("1. Sube el Catálogo de Productos para validar", type=["xlsx"])

if file_cat:
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    catalogo = df_cat.drop_duplicates(subset=['Código']).set_index('Código').to_dict('index')

    st.divider()
    fecha_inicio_plan = st.date_input("📅 Fecha de inicio de producción", datetime.now())

    # 2. Entrada de Datos Masiva
    st.subheader("📝 Entrada de Pedidos (Copiar y Pegar)")
    
    if "data_editor_input" not in st.session_state:
        st.session_state.data_editor_input = pd.DataFrame(columns=["Código", "Cantidad", "Setup"])

    # El editor permite pegar desde Excel
    edited_df = st.data_editor(
        st.session_state.data_editor_input,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Código": st.column_config.TextColumn("Código", help="Pega aquí los códigos"),
            "Cantidad": st.column_config.NumberColumn("Cantidad (kg)", min_value=0),
            "Setup": st.column_config.NumberColumn("Setup (horas)", min_value=0)
        },
        key="editor_masivo"
    )
    st.session_state.data_editor_input = edited_df

    # 3. Procesamiento y Cálculo
    if not edited_df.dropna(subset=['Código']).empty:
        st.divider()
        st.subheader("📅 Cronograma Calculado")
        
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_inicio)
        plan_calculado = []

        for _, fila in edited_df.iterrows():
            cod_str = str(fila['Código']).strip()
            
            # Solo procesar si el código existe en el catálogo
            if cod_str in catalogo:
                info = catalogo[cod_str]
                tasa_kgh = float(info['Tasa']) * 1000
                peso_u = float(info.get('Peso unitario', 0))
                
                # Setup
                rem_s = float(fila['Setup']) if pd.notna(fila['Setup']) else 0
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
                
                inicio_prod = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                
                # Producción
                rem_c = float(fila['Cantidad']) if pd.notna(fila['Cantidad']) else 0
                while rem_c > 0.001:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    cap_kg = ((obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                    prod_kg = min(rem_c, cap_kg)
                    tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
                
                plan_calculado.append({
                    "CÓDIGO": cod_str,
                    "PRODUCTO": info['Producto'],
                    "KG": fila['Cantidad'],
                    "UNIDADES": round(fila['Cantidad'] / peso_u, 0) if peso_u > 0 else 0,
                    "INICIO": inicio_prod.strftime('%d/%m/%y %I:%M %p'),
                    "FIN": tiempo_actual.strftime('%d/%m/%y %I:%M %p')
                })

        if plan_calculado:
            df_final = pd.DataFrame(plan_calculado)
            st.dataframe(df_final, use_container_width=True)

            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("🗑️ Limpiar Tabla", type="primary"):
                    confirmar_borrar_todo()
            with col2:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, sheet_name='Plan', index=False)
                st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Plan_Produccion.xlsx")
        else:
            st.warning("Introduce códigos válidos del catálogo para ver el cronograma.")

else:
    st.info("👋 Sube el Catálogo para habilitar la tabla de ingreso.")
