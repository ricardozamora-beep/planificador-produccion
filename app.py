import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import plotly.express as px

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador Pro - Heredia", page_icon="🏭", layout="wide")

# --- LÓGICA DE TURNOS ---
def obtener_fin_turno(dt, hora_lun_jue, hora_vie):
    hora_fin = hora_lun_jue if dt.weekday() <= 3 else hora_vie
    return dt.replace(hour=hora_fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, lista_feriados, hora_inicio_turno, hora_lun_jue, hora_vie):
    while True:
        dia_semana = dt.weekday()
        fecha_actual_str = dt.strftime("%Y-%m-%d")
        
        # Si es fin de semana o feriado
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
        return dt

# --- INTERFAZ LATERAL (CONFIGURACIÓN) ---
st.sidebar.header("⚙️ Configuración de Planta")

# 1. Selector de Turnos
st.sidebar.subheader("Horarios de Salida")
h_inicio = st.sidebar.number_input("Hora de Inicio (24h)", min_value=0, max_value=23, value=7)
h_lun_jue = st.sidebar.number_input("Lunes a Jueves (24h)", min_value=0, max_value=23, value=17)
h_vie = st.sidebar.number_input("Viernes (24h)", min_value=0, max_value=23, value=15)

# 2. Editor de Feriados
st.sidebar.subheader("Calendario de Feriados")
feriados_seleccionados = st.sidebar.date_input(
    "Selecciona días no laborales",
    value=[],
    help="Haz clic para añadir feriados o días de cierre."
)
lista_feriados = [d.strftime("%Y-%m-%d") for d in feriados_seleccionados]

# --- CUERPO PRINCIPAL ---
st.title("🏭 Planificador de Producción Avanzado")
st.markdown("Ajusta los horarios y feriados en el panel izquierdo antes de procesar.")

col1, col2 = st.columns(2)
with col1:
    file_cat = st.file_uploader("📂 Subir Catálogo (Ton/h)", type=["xlsx"])
with col2:
    file_ped = st.file_uploader("📦 Subir Pedidos (Kg)", type=["xlsx"])

if file_cat and file_ped:
    try:
        df_cat = pd.read_excel(file_cat)
        df_ped = pd.read_excel(file_ped)
        
        # Determinar fecha de inicio del plan
        fecha_inicio_plan = st.date_input("Fecha de inicio de producción", datetime.now())
        tiempo_actual = datetime.combine(fecha_inicio_plan, datetime.min.time()).replace(hour=h_inicio)
        
        # Procesamiento
        df_cat.columns = df_cat.columns.str.strip()
        df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
        catalogo = df_cat[df_cat['Tasa'] > 0].drop_duplicates('Código').set_index('Código').to_dict('index')
        
        plan_prod, diario = [], {}
        df_ped.columns = df_ped.columns.str.strip()
        df_items = df_ped[df_ped['Código'].notna() & df_ped['Cantidad'].notna()].copy()

        for _, fila in df_items.iterrows():
            cod = str(fila['Código']).strip()
            if cod not in catalogo: continue
            
            info = catalogo[cod]
            tasa_kgh = float(info['Tasa']) * 1000
            peso_pedido_kg = float(fila['Cantidad'])
            peso_u_kg = float(info.get('Peso unitario', 0))
            setup_especifico = float(fila.get('Setup', 0))
            
            # Aplicar Setup
            if setup_especifico > 0:
                rem_s = setup_especifico
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                    espacio = (obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600
                    cons = min(rem_s, espacio)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
            
            inicio_p = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
            
            # Aplicar Producción
            rem_c = peso_pedido_kg
            while rem_c > 0.001:
                tiempo_actual = saltar_no_laborales(tiempo_actual, lista_feriados, h_inicio, h_lun_jue, h_vie)
                f_hoy = tiempo_actual.strftime('%Y-%m-%d')
                cap_kg = ((obtener_fin_turno(tiempo_actual, h_lun_jue, h_vie) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                prod_kg = min(rem_c, cap_kg)
                diario[f_hoy] = diario.get(f_hoy, 0) + prod_kg
                tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
            
            plan_prod.append({
                "CÓDIGO": cod, "PRODUCTO": info['Producto'], "KG": peso_pedido_kg,
                "UNIDADES": round(peso_pedido_kg / peso_u_kg, 0) if peso_u_kg > 0 else 0,
                "INICIO": inicio_p.strftime('%d/%m/%Y %H:%M'), "FIN": tiempo_actual.strftime('%d/%m/%Y %H:%M')
            })

        if plan_prod:
            # Crear reporte
            df_detalle = pd.DataFrame(plan_prod)
            df_diario_real = pd.DataFrame(list(diario.items()), columns=['FECHA', 'KG']).sort_values('FECHA')
            
            st.success("✅ Planificación generada.")
            
            # Visualización: Gráfico de Carga
            fig = px.bar(df_diario_real, x='FECHA', y='KG', title="Carga Diaria de Producción", color_discrete_sequence=['#1F4E78'])
            st.plotly_chart(fig, use_container_width=True)
            
            # Botón de Descarga (Excel Formateado)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_detalle.to_excel(writer, sheet_name='Plan', index=False)
                # (Aquí puedes mantener el código de formateo de colores que usamos antes)
            
            st.download_button("📥 Descargar Excel", data=output.getvalue(), file_name="Plan_Heredia.xlsx")
            st.dataframe(df_detalle, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
