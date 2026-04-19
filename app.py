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

# --- SIDEBAR: CONFIGURACIÓN ---
st.sidebar.header("⚙️ Configuración de Planta")
h_inicio = st.sidebar.number_input("Hora Inicio Turno", 0, 23, 7)
h_lun_jue = st.sidebar.number_input("Salida Lun-Jue", 0, 23, 17)
h_vie = st.sidebar.number_input("Salida Viernes", 0, 23, 15)
feriados_sel = st.sidebar.date_input("Días Feriados", value=[])
lista_feriados = [d.strftime("%Y-%m-%d") for d in feriados_sel]

# --- CUERPO PRINCIPAL ---
st.title("⏱️ Planificador de Producción Masivo")

file_cat = st.file_uploader("1. Sube el Catálogo de Productos", type=["xlsx"])

if file_cat:
    df_cat = pd.read_excel(file_cat)
    df_cat.columns = df_cat.columns.str.strip()
    df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
    catalogo = df_cat.drop_duplicates(subset=['Código']).set_index('Código').to_dict('index')

    st.divider()
    
    # 2. ZONA DE PEGADO MASIVO
    st.subheader("🚀 Pegado Rápido desde Excel")
    st.markdown("""
    1. Copia tus columnas en Excel (**Código**, **Cantidad**, **Setup**).
    2. Pégalas en el cuadro de abajo.
    3. Presiona **Ctrl+Enter** (o haz clic fuera) para cargar los datos.
    """)
    
    raw_data = st.text_area("Pega aquí (Columnas separadas por tabulación o espacio):", height=150, placeholder="Ejemplo:\nCOD123  5000  1.5\nCOD456  2000  0.5")

    # Procesar el texto pegado
    input_data = []
    if raw_data:
        lines = raw_data.strip().split('\n')
        for line in lines:
            parts = line.split() # Separa por espacios o tabs
            if len(parts) >= 2:
                cod = parts[0].strip()
                cant = parts[1].replace(',', '') # Limpiar comas de miles si vienen de Excel
                setup = parts[2] if len(parts) > 2 else 0
                input_data.append({"Código": cod, "Cantidad": float(cant), "Setup": float(setup)})
    
    df_input = pd.DataFrame(input_data)

    if not df_input.empty:
        st.success(f"Se cargaron {len(df_input)} registros.")
        
        # Permitir edición final en la tabla por si algo quedó mal
        st.subheader("📝 Revisión de Datos Cargados")
        final_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

        # 3. Cálculo del Cronograma
        st.divider()
        fecha_inicio_plan = st.date_input("📅 Fecha de inicio", datetime.now())
        
        if st.button("Calcular Cronograma Final"):
            tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_inicio)
            plan_calculado = []

            for _, fila in final_df.iterrows():
                cod_str = str(fila['Código']).strip()
                
                if cod_str in catalogo:
                    info = catalogo[cod_str]
                    tasa_kgh = float(info['Tasa']) * 1000
                    peso_u = float(info.get('Peso unitario', 0))
                    
                    # Setup
                    rem_s = float(fila['Setup'])
                    while rem_s > 0:
                        tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                        espacio = (obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600
                        cons = min(rem_s, espacio)
                        tiempo_actual += timedelta(hours=cons); rem_s -= cons
                    
                    inicio_prod = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    
                    # Producción
                    rem_c = float(fila['Cantidad'])
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
                df_res = pd.DataFrame(plan_calculado)
                st.dataframe(df_res, use_container_width=True)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_res.to_excel(writer, sheet_name='Plan', index=False)
                st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Plan_Produccion.xlsx")
    
else:
    st.info("👋 Sube el Catálogo para habilitar el pegado masivo.")
