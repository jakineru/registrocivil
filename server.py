from flask import Flask, request, jsonify
from unidecode import unidecode
from flask_cors import CORS # Necesario para permitir solicitudes desde el navegador

app = Flask(__name__)
CORS(app) # Habilita CORS para todas las rutas

DATA = [] # Variable global para almacenar los datos cargados
LUGARES_MAP = {} # Diccionario global para almacenar el mapeo de lugares

# Función para cargar los datos desde múltiples archivos (TXT, CSV y lugares.txt)
def load_data(data_filenames=['cedulas_1.txt', 'cedulas_2.txt', 'resultados_cedulas.csv'], lugares_filename='lugares.txt'):
    global DATA
    global LUGARES_MAP
    temp_data = {} # {ci: {data_dict}}

    print("\n--- Iniciando carga de datos ---")

    # Primero, cargar el mapeo de lugares desde lugares.txt
    print(f"Procesando archivo de lugares: {lugares_filename}")
    try:
        with open(lugares_filename, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                parts = line.strip().split(',', 1) # Divide solo por la primera coma
                if len(parts) == 2:
                    code = parts[0].strip()
                    name = parts[1].strip()
                    LUGARES_MAP[code] = name
                else:
                    print(f"Advertencia: Línea {line_num} con formato inesperado en {lugares_filename}: '{line.strip()}'")
        print(f"Cargado LUGARES_MAP: {LUGARES_MAP}")
    except FileNotFoundError:
        print(f"Advertencia: {lugares_filename} no encontrado. No se aplicará el mapeo de lugares.")
    except Exception as e:
        print(f"Ocurrió un error al cargar los datos desde {lugares_filename}: {e}")

    # Luego, cargar los archivos de datos principales (TXT y CSV)
    for filename in data_filenames:
        print(f"Procesando archivo: {filename}")
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    parts = line.strip().split(',')
                    ci = None # Inicializar ci para evitar errores si no se parsea correctamente
                    current_entry = {}

                    if len(parts) == 3: # Formato CI,NOMBRES,APELLIDOS (de los TXT)
                        ci, nombres, apellidos = parts
                        current_entry = {'ci': ci, 'nombres': nombres, 'apellidos': apellidos}
                    elif len(parts) == 5: # Formato CI,NOMBRES,APELLIDOS,FECHA_NACIMIENTO,LUGAR_NACIMIENTO (del CSV)
                        ci, nombres, apellidos, fecha_nacimiento, lugar_nacimiento_raw = parts
                        
                        lugar_nacimiento_formatted = lugar_nacimiento_raw.strip()

                        # DEBUG: Mostrar el valor crudo y el mapa antes de intentar el mapeo
                        lugar_nacimiento_stripped = lugar_nacimiento_raw.strip()
                        print(f"  DEBUG: Procesando lugar_nacimiento_raw: '{lugar_nacimiento_raw}' (stripped: '{lugar_nacimiento_stripped}')")
                        print(f"  DEBUG: LUGARES_MAP keys: {list(LUGARES_MAP.keys())}")

                        # 1. Intentar mapear usando LUGARES_MAP (ej: "Rocha 4" -> "Castillos (Rocha 4)")
                        if lugar_nacimiento_stripped in LUGARES_MAP:
                            localidad = LUGARES_MAP[lugar_nacimiento_stripped]
                            departamento_code = lugar_nacimiento_stripped # El código es el departamento
                            lugar_nacimiento_formatted = f"{localidad} ({departamento_code})"
                            print(f"  DEBUG: Transformado lugar: '{lugar_nacimiento_raw}' a '{lugar_nacimiento_formatted}' usando mapeo.")
                        # 2. Si no hay mapeo, intentar formatear si contiene una coma (ej: "Rocha,Castillos" -> "Castillos (Rocha)")
                        elif ',' in lugar_nacimiento_raw:
                            lugar_parts = lugar_nacimiento_raw.split(',', 1)
                            if len(lugar_parts) == 2:
                                localidad = lugar_parts[1].strip()
                                departamento = lugar_parts[0].strip()
                                lugar_nacimiento_formatted = f"{localidad} ({departamento})"
                            else:
                                lugar_nacimiento_formatted = lugar_nacimiento_raw.strip() # En caso de formato inesperado con coma
                            print(f"  DEBUG: Formateado lugar con coma: '{lugar_nacimiento_raw}' a '{lugar_nacimiento_formatted}'.")
                        # 3. Si no hay mapeo ni coma, mantener el valor original
                        else:
                            lugar_nacimiento_formatted = lugar_nacimiento_raw.strip()
                            print(f"  DEBUG: Lugar sin cambio: '{lugar_nacimiento_raw}' (no mapeado y sin coma).")


                        current_entry = {
                            'ci': ci,
                            'nombres': nombres,
                            'apellidos': apellidos,
                            'fecha_nacimiento': fecha_nacimiento,
                            'lugar_nacimiento': lugar_nacimiento_formatted # Usar el formato transformado
                        }
                    else:
                        print(f"Advertencia: Línea {line_num} con formato inesperado en {filename}: '{line.strip()}'")
                        continue # Salta a la siguiente línea si el formato no es el esperado

                    if ci: # Solo procesar si la CI fue extraída
                        # Lógica para manejar duplicados: priorizar la entrada más completa
                        if ci in temp_data:
                            existing_entry = temp_data[ci]
                            # Si la entrada existente tiene 3 campos (TXT) y la nueva tiene 5 (CSV), la nueva es más completa
                            if len(existing_entry) == 3 and len(current_entry) == 5:
                                temp_data[ci] = current_entry
                                print(f"  CI: {ci} - Priorizando entrada CSV (5 campos) desde '{filename}' sobre TXT (3 campos).")
                            # Si ambas tienen el mismo número de campos, sobrescribe con la última cargada
                            elif len(existing_entry) == len(current_entry):
                                 temp_data[ci] = current_entry
                            # Si la existente ya tiene 5 campos y la nueva tiene 3, mantenemos la existente
                            else:
                                pass
                        else:
                            temp_data[ci] = current_entry # Si no existe, añadirla
            print(f"Datos procesados desde {filename}. Entradas únicas en temp_data: {len(temp_data)}")
        except FileNotFoundError:
            print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista en la misma carpeta que server.py.")
        except Exception as e:
            print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")
    
    DATA = list(temp_data.values()) # Convierte el diccionario de nuevo a una lista
    if not DATA:
        print("Error: No se cargaron datos de ningún archivo. Asegúrate de que los archivos existan y contengan datos.")
    else:
        print(f"\n--- Carga de datos finalizada ---")
        print(f"Total de entradas únicas y priorizadas en DATA: {len(DATA)}")

# Funciones de búsqueda (sin cambios, operan sobre DATA combinada y priorizada)
def buscar_ci(ci_to_search):
    for entry in DATA:
        if entry['ci'] == ci_to_search:
            return entry
    return None

def buscar_por_nombres(nombres_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    for entry in DATA:
        if nombres_to_search_lower in unidecode(entry['nombres'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_apellidos(apellido_to_search):
    coincidencias = []
    apellido_to_search_lower = unidecode(apellido_to_search.lower())
    for entry in DATA:
        if apellido_to_search_lower in unidecode(entry['apellidos'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_nombres_y_apellidos(nombres_to_search, apellidos_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    apellidos_to_search_lower = unidecode(apellidos_to_search.lower())
    
    print(f"\n--- Búsqueda por Nombre y Apellido: '{nombres_to_search_lower}' y '{apellidos_to_search_lower}' ---")
    print(f"Total de entradas en DATA para buscar: {len(DATA)}")
    
    for entry in DATA:
        entry_nombres_lower = unidecode(entry['nombres'].lower())
        entry_apellidos_lower = unidecode(entry['apellidos'].lower())
        
        if (nombres_to_search_lower in entry_nombres_lower and
            apellidos_to_search_lower in entry_apellidos_lower):
            coincidencias.append(entry)
            print(f"  Coincidencia encontrada: CI={entry['ci']}, Nombres='{entry['nombres']}', Apellidos='{entry['apellidos']}'")
            
    print(f"Total de coincidencias encontradas: {len(coincidencias)}")
    return coincidencias

# Ruta API para la búsqueda
@app.route('/search', methods=['POST'])
def search():
    data = request.json
    nombre = data.get('nombre', '').strip()
    apellido = data.get('apellido', '').strip()
    cedula = data.get('cedula', '').strip()

    results = []
    search_type = "No se realizó búsqueda"

    # La lógica de búsqueda prioriza la cédula, luego nombre+apellido, luego nombre, luego apellido.
    if cedula:
        result = buscar_ci(cedula)
        if result:
            results = [result]
        search_type = "Cédula"
    elif nombre and apellido:
        results = buscar_por_nombres_y_apellidos(nombre, apellido)
        search_type = "Nombre y Apellido"
    elif nombre:
        results = buscar_por_nombres(nombre)
        search_type = "Nombre"
    elif apellido:
        results = buscar_por_apellidos(apellido)
        search_type = "Apellido"

    return jsonify({'results': results, 'search_type': search_type})

# Ruta API para verificar el estado del servidor (si los datos están cargados)
@app.route('/status', methods=['GET'])
def status():
    if DATA:
        return jsonify({'status': 'ready', 'message': f'Datos cargados: {len(DATA)} entradas'})
    else:
        return jsonify({'status': 'loading', 'message': 'Datos aún no cargados o archivo(s) no encontrado(s)'})

if __name__ == '__main__':
    # Llama a load_data con los nombres de tus archivos TXT y CSV
    # Asegúrate de que 'lugares.txt' esté en la misma carpeta
    load_data(data_filenames=['cedulas_1.txt', 'cedulas_2.txt', 'resultados_cedulas.csv'], lugares_filename='lugares.txt')
    app.run(debug=True, port=5000) # Ejecuta el servidor en el puerto 5000
