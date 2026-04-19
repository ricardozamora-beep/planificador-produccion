# Procesar el texto pegado de forma segura
    input_data = []
    if raw_data:
        lines = raw_data.strip().split('\n')
        for line in lines:
            # Separar por tabulaciones (lo normal al copiar de Excel) o espacios
            parts = line.replace('\t', ' ').split() 
            if len(parts) >= 2:
                try:
                    cod = parts[0].strip()
                    # Limpiamos puntos de miles y convertimos a float
                    cant_str = parts[1].replace(',', '').strip()
                    cant = float(cant_str)
                    
                    # Intentamos leer el setup, si no existe o falla, ponemos 0
                    try:
                        setup_val = parts[2].strip() if len(parts) > 2 else "0"
                        setup = float(setup_val)
                    except (ValueError, IndexError):
                        setup = 0.0
                        
                    input_data.append({"Código": cod, "Cantidad": cant, "Setup": setup})
                except ValueError:
                    # Si la cantidad no es un número, ignoramos esa línea (como encabezados)
                    continue
