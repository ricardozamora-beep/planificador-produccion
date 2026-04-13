import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Planificador de Producción", page_icon="🏭")

# --- LÓGICA DE NEGOCIO (EL MOTOR) ---
def obtener_fin_turno(dt):
    hora_fin = 17 if dt.weekday() <= 3 else 15
    return dt.replace(hour=hora_fin, minute=0, second=0, microsecond=0)

def saltar_no_laborales(dt, lista_feriados):
    while True:
        dia_semana = dt.weekday()
        fecha_actual_str = dt.strftime("%Y-%m-%d")
        if dia_semana >= 5 or fecha_actual_str in lista_feriados:
            dt = (dt + timedelta(days=1)).replace(hour=7, minute=0, second=0)
            continue
        hora_salida = 17 if dia_semana <= 3 else 15
        if dt.hour >= hora_salida:
            dt = (dt + timedelta(days=1)).replace(hour=7, minute=0, second=0)
            continue
        if dt.hour < 7:
            dt = dt.replace(hour=7, minute=0, second=0)
        return dt

# --- INTERFAZ DE USUARIO ---
st.title("🏭 Planificador de Producción Automático")
st.markdown("Sube tus archivos de Excel para generar el cronograma de producción.")

col1, col2 = st.columns(2)

with col1:
    file_cat = st.file_uploader("Subir Catálogo", type=["xlsx"])
with col2:
    file_ped = st.file_uploader("Subir Pedidos", type=["xlsx"])

if file_cat and file_ped:
    try:
        df_cat = pd.read_excel(file_cat)
        df_ped = pd.read_excel(file_ped)
        
        # --- EXTRACCIÓN DE CONFIGURACIÓN ---
        inicio_dt, feriados = None, []
        for r in range(min(40, len(df_ped))):
            for c in range(min(20, len(df_ped.columns))):
                val = str(df_ped.iloc[r, c]).strip().lower()
                if val == "inicio": 
                    inicio_dt = pd.to_datetime(df_ped.iloc[r, c+1], dayfirst=True, errors='coerce')
                elif val == "feriados":
                    for f in df_ped.iloc[r+1:, c].dropna():
                        f_dt = pd.to_datetime(f, dayfirst=True, errors='coerce')
                        if pd.notna(f_dt): feriados.append(f_dt.strftime("%Y-%m-%d"))

        if pd.isna(inicio_dt) or inicio_dt is None:
            inicio_dt = datetime.now()
        
        tiempo_actual = saltar_no_laborales(inicio_dt, feriados)
        
        # --- PROCESAMIENTO ---
        df_cat.columns = df_cat.columns.str.strip()
        df_cat['Código'] = df_cat['Código'].astype(str).str.strip()
        catalogo = df_cat[df_cat['Tasa'] > 0].drop_duplicates('Código').set_index('Código').to_dict('index')
        
        plan_prod, diario = [], {}
        df_ped.columns = df_ped.columns.str.strip()
        df_items = df_ped[df_ped['Código'].notna() & df_ped['Cantidad'].notna()].copy()

        for _, fila in df_items.iterrows():
            cod = str(fila['Código']).strip()
            if cod.lower() in ['inicio', 'feriados'] or cod not in catalogo: continue
            
            info = catalogo[cod]
            tasa_kgh = float(info['Tasa']) * 1000
            peso_pedido_kg = float(fila['Cantidad'])
            peso_u_kg = float(info.get('Peso unitario', 0))
            setup_especifico = float(fila.get('Setup', 0))
            
            # Setup
            if setup_especifico > 0:
                rem_s = setup_especifico
                while rem_s > 0:
                    tiempo_actual = saltar_no_laborales(tiempo_actual, feriados)
                    cons = min(rem_s, (obtener_fin_turno(tiempo_actual) - tiempo_actual).total_seconds()/3600)
                    tiempo_actual += timedelta(hours=cons); rem_s -= cons
            
            inicio_p = saltar_no_laborales(tiempo_actual, feriados)
            
            # Producción
            rem_c = peso_pedido_kg
            while rem_c > 0.001:
                tiempo_actual = saltar_no_laborales(tiempo_actual, feriados)
                f_hoy = tiempo_actual.strftime('%Y-%m-%d')
                cap_kg = ((obtener_fin_turno(tiempo_actual) - tiempo_actual).total_seconds()/3600) * tasa_kgh
                prod_kg = min(rem_c, cap_kg)
                diario[f_hoy] = diario.get(f_hoy, 0) + prod_kg
                tiempo_actual += timedelta(hours=prod_kg / tasa_kgh); rem_c -= prod_kg
            
            plan_prod.append({
                "CÓDIGO": cod, "PRODUCTO": info['Producto'], "KG": peso_pedido_kg,
                "UNIDADES": round(peso_pedido_kg / peso_u_kg, 0) if peso_u_kg > 0 else 0,
                "FECHA INICIO": inicio_p.strftime('%d/%m/%Y'), "HORA INICIO": inicio_p.strftime('%I:%M %p'),
                "FECHA FIN": tiempo_actual.strftime('%d/%m/%Y'), "HORA FIN": tiempo_actual.strftime('%I:%M %p')
            })

        if plan_prod:
            st.success("✅ ¡Planificación calculada con éxito!")
            
            # Crear Excel en memoria
            output = io.BytesIO()
            df_detalle = pd.DataFrame(plan_prod)
            df_diario = pd.DataFrame(list(diario.items()), columns=['FECHA', 'KG TOTAL DÍA']).sort_values('FECHA')
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_detalle.to_excel(writer, sheet_name='Detalle', index=False)
                df_diario.to_excel(writer, sheet_name='Diario', index=False)
            
            st.download_button(
                label="📥 Descargar Plan de Producción",
                data=output.getvalue(),
                file_name=f"Plan_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            st.subheader("Vista Previa del Detalle")
            st.dataframe(df_detalle)
            
    except Exception as e:
        st.error(f"Hubo un problema: {e}")