from flask import Flask, request, jsonify
from unidecode import unidecode
from flask_cors import CORS # Necesario para permitir solicitudes desde el navegador

app = Flask(__name__)
CORS(app) # Habilita CORS para todas las rutas

DATA = [] # Variable global para almacenar los datos cargados como lista
DATA_BY_CI = {} # Diccionario para búsquedas rápidas por CI
LUGARES_MAP = {} # Diccionario para el mapeo de lugares

# Nuevos índices para búsquedas rápidas por nombre y apellido
NAMES_WORD_INDEX = {}    # { 'palabra': {ci1, ci2, ...} }
APELLIDOS_WORD_INDEX = {} # { 'palabra': {ci1, ci2, ...} }

# Función auxiliar para añadir una palabra a un índice
def add_to_index(index_map, word, ci):
    # Normaliza la palabra para el índice
    normalized_word = unidecode(word.lower())
    if normalized_word: # Asegurarse de que la palabra no esté vacía
        if normalized_word not in index_map:
            index_map[normalized_word] = set()
        index_map[normalized_word].add(ci)

# Función para cargar los datos desde múltiples archivos (TXT, CSV y lugares.txt)
def load_data(data_filenames=['cedulas_1.txt', 'cedulas_2.txt', 'resultados_cedulas.csv'], lugares_filename='lugares.txt'):
    global DATA
    global DATA_BY_CI
    global LUGARES_MAP
    global NAMES_WORD_INDEX
    global APELLIDOS_WORD_INDEX

    temp_data = {} # {ci: {data_dict}}
    NAMES_WORD_INDEX = {} # Reiniciar índices al cargar
    APELLIDOS_WORD_INDEX = {} # Reiniciar índices al cargar

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
                    ci = None
                    current_entry = {}

                    if len(parts) == 3: # Formato CI,NOMBRES,APELLIDOS (de los TXT)
                        ci, nombres, apellidos = parts
                        current_entry = {'ci': ci, 'nombres': nombres, 'apellidos': apellidos}
                    elif len(parts) == 5: # Formato CI,NOMBRES,APELLIDOS,FECHA_NACIMIENTO,LUGAR_NACIMIENTO (del CSV)
                        ci, nombres, apellidos, fecha_nacimiento, lugar_nacimiento_raw = parts
                        
                        lugar_nacimiento_formatted = lugar_nacimiento_raw.strip()

                        lugar_nacimiento_stripped = lugar_nacimiento_raw.strip()

                        # 1. Intentar mapear usando LUGARES_MAP
                        if lugar_nacimiento_stripped in LUGARES_MAP:
                            localidad = LUGARES_MAP[lugar_nacimiento_stripped]
                            departamento_code = lugar_nacimiento_stripped
                            lugar_nacimiento_formatted = f"{localidad} ({departamento_code})"
                        # 2. Si no hay mapeo, intentar formatear si contiene una coma
                        elif ',' in lugar_nacimiento_raw:
                            lugar_parts = lugar_nacimiento_raw.split(',', 1)
                            if len(lugar_parts) == 2:
                                localidad = lugar_parts[1].strip()
                                departamento = lugar_parts[0].strip()
                                lugar_nacimiento_formatted = f"{localidad} ({departamento})"
                            else:
                                lugar_nacimiento_formatted = lugar_nacimiento_raw.strip()
                        # 3. Si no hay mapeo ni coma, mantener el valor original
                        else:
                            lugar_nacimiento_formatted = lugar_nacimiento_raw.strip()

                        current_entry = {
                            'ci': ci,
                            'nombres': nombres,
                            'apellidos': apellidos,
                            'fecha_nacimiento': fecha_nacimiento,
                            'lugar_nacimiento': lugar_nacimiento_formatted
                        }
                    else:
                        print(f"Advertencia: Línea {line_num} con formato inesperado en {filename}: '{line.strip()}'")
                        continue

                    if ci:
                        # Lógica para manejar duplicados: priorizar la entrada más completa
                        if ci in temp_data:
                            existing_entry = temp_data[ci]
                            if len(existing_entry) == 3 and len(current_entry) == 5:
                                temp_data[ci] = current_entry
                                # print(f"  CI: {ci} - Priorizando entrada CSV (5 campos) desde '{filename}' sobre TXT (3 campos).")
                            elif len(existing_entry) == len(current_entry):
                                 temp_data[ci] = current_entry
                            else:
                                pass
                        else:
                            temp_data[ci] = current_entry
            print(f"Datos procesados desde {filename}. Entradas únicas en temp_data: {len(temp_data)}")
        except FileNotFoundError:
            print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista en la misma carpeta que server.py.")
        except Exception as e:
            print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")
    
    DATA = list(temp_data.values())
    DATA_BY_CI = {entry['ci']: entry for entry in DATA} # Rellena el diccionario de CI para búsquedas rápidas

    # Construir los índices de palabras para nombres y apellidos
    print("\n--- Construyendo índices de nombres y apellidos ---")
    for entry in DATA:
        ci = entry['ci']
        
        # Indexar nombres
        nombres_words = unidecode(entry['nombres'].lower()).split()
        for word in nombres_words:
            add_to_index(NAMES_WORD_INDEX, word, ci)

        # Indexar apellidos
        apellidos_words = unidecode(entry['apellidos'].lower()).split()
        for word in apellidos_words:
            add_to_index(APELLIDOS_WORD_INDEX, word, ci)
    
    if not DATA:
        print("Error: No se cargaron datos de ningún archivo. Asegúrate de que los archivos existan y contengan datos.")
    else:
        print(f"\n--- Carga de datos finalizada ---")
        print(f"Total de entradas únicas y priorizadas en DATA (lista): {len(DATA)}")
        print(f"Total de entradas en DATA_BY_CI (diccionario): {len(DATA_BY_CI)}")
        print(f"Total de palabras indexadas en Nombres: {len(NAMES_WORD_INDEX)}")
        print(f"Total de palabras indexadas en Apellidos: {len(APELLIDOS_WORD_INDEX)}")


# Funciones de búsqueda (buscar_ci usa DATA_BY_CI, las otras usan índices)
def buscar_ci(ci_to_search):
    return DATA_BY_CI.get(ci_to_search)

def buscar_por_nombres(nombres_to_search):
    coincidencias_cis = set()
    nombres_search_words = unidecode(nombres_to_search.lower()).split()

    if not nombres_search_words:
        return []

    # Iniciar con el conjunto de CIs del primer término
    first_word = nombres_search_words[0]
    coincidencias_cis = NAMES_WORD_INDEX.get(first_word, set()).copy()

    # Intersecar con los CIs de los términos restantes
    for i in range(1, len(nombres_search_words)):
        word = nombres_search_words[i]
        coincidencias_cis.intersection_update(NAMES_WORD_INDEX.get(word, set()))
        if not coincidencias_cis: # Si el conjunto se vacía, no hay más coincidencias
            break
    
    # Recuperar los objetos completos de DATA_BY_CI
    results = [DATA_BY_CI[ci] for ci in coincidencias_cis if ci in DATA_BY_CI]
    return results

def buscar_por_apellidos(apellido_to_search):
    coincidencias_cis = set()
    apellidos_search_words = unidecode(apellido_to_search.lower()).split()

    if not apellidos_search_words:
        return []

    # Iniciar con el conjunto de CIs del primer término
    first_word = apellidos_search_words[0]
    coincidencias_cis = APELLIDOS_WORD_INDEX.get(first_word, set()).copy()

    # Intersecar con los CIs de los términos restantes
    for i in range(1, len(apellidos_search_words)):
        word = apellidos_search_words[i]
        coincidencias_cis.intersection_update(APELLIDOS_WORD_INDEX.get(word, set()))
        if not coincidencias_cis:
            break
            
    results = [DATA_BY_CI[ci] for ci in coincidencias_cis if ci in DATA_BY_CI]
    return results

def buscar_por_nombres_y_apellidos(nombres_to_search, apellidos_to_search):
    nombres_search_words = unidecode(nombres_to_search.lower()).split()
    apellidos_search_words = unidecode(apellidos_to_search.lower()).split()

    # Conjuntos de CIs que coinciden con los nombres y apellidos
    cis_from_names = set(DATA_BY_CI.keys()) if nombres_search_words else set()
    cis_from_apellidos = set(DATA_BY_CI.keys()) if apellidos_search_words else set()

    if nombres_search_words:
        first_name_word = nombres_search_words[0]
        cis_from_names = NAMES_WORD_INDEX.get(first_name_word, set()).copy()
        for i in range(1, len(nombres_search_words)):
            word = nombres_search_words[i]
            cis_from_names.intersection_update(NAMES_WORD_INDEX.get(word, set()))
            if not cis_from_names: break

    if apellidos_search_words:
        first_apellido_word = apellidos_search_words[0]
        cis_from_apellidos = APELLIDOS_WORD_INDEX.get(first_apellido_word, set()).copy()
        for i in range(1, len(apellidos_search_words)):
            word = apellidos_search_words[i]
            cis_from_apellidos.intersection_update(APELLIDOS_WORD_INDEX.get(word, set()))
            if not cis_from_apellidos: break

    # Si ambos campos tienen términos de búsqueda, encontrar la intersección de los CIs
    if nombres_search_words and apellidos_search_words:
        final_matching_cis = cis_from_names.intersection(cis_from_apellidos)
    elif nombres_search_words:
        final_matching_cis = cis_from_names
    elif apellidos_search_words:
        final_matching_cis = cis_from_apellidos
    else:
        final_matching_cis = set() # No hay términos de búsqueda válidos

    results = [DATA_BY_CI[ci] for ci in final_matching_cis if ci in DATA_BY_CI]
    
    print(f"\n--- Búsqueda por Nombre y Apellido: '{nombres_to_search}' y '{apellidos_to_search}' ---")
    print(f"Total de entradas en DATA para buscar: {len(DATA)}")
    print(f"Coincidencias de nombres (CIs): {len(cis_from_names)}")
    print(f"Coincidencias de apellidos (CIs): {len(cis_from_apellidos)}")
    print(f"Total de coincidencias encontradas: {len(results)}")
    
    return results

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
