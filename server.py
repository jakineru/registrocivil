from flask import Flask, request, jsonify
from unidecode import unidecode
from flask_cors import CORS # Necesario para permitir solicitudes desde el navegador
import csv

app = Flask(__name__)
CORS(app) # Habilita CORS para todas las rutas

DATA_LEGACY = [] # Variable global para almacenar los datos de cedulas_partX.txt
DATA_NEW = []    # Variable global para almacenar los datos de resultados_cedulas.csv

# Función para cargar los datos desde resultados_cedulas.csv
def load_new_data(filename='resultados_cedulas.csv'):
    global DATA_NEW
    DATA_NEW = [] # Limpiar datos existentes antes de cargar
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            # Asumiendo que la primera fila no es un encabezado o que los datos comienzan directamente
            # Si hay un encabezado, puedes usar next(reader) para saltarlo
            for row in reader:
                if len(row) == 5: # cedula,nombre,apellido,fechadenacimiento,lugardenacimiento
                    ci, nombres, apellidos, fecha_nacimiento, lugar_nacimiento = row
                    DATA_NEW.append({
                        'ci': ci,
                        'nombres': nombres,
                        'apellidos': apellidos,
                        'fecha_nacimiento': fecha_nacimiento,
                        'lugar_nacimiento': lugar_nacimiento
                    })
        print(f"Datos cargados exitosamente desde {filename}. Total de entradas: {len(DATA_NEW)}")
    except FileNotFoundError:
        print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista y contenga datos.")
    except Exception as e:
        print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")

# Función para cargar los datos desde múltiples archivos (cedulas_partX.txt)
def load_legacy_data(filenames=['cedulas_part1.txt', 'cedulas_part2.txt']):
    global DATA_LEGACY
    DATA_LEGACY = [] # Limpiar datos existentes antes de cargar
    for filename in filenames:
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                for line in file:
                    parts = line.strip().split(',')
                    if len(parts) == 3: # ci,nombres,apellidos
                        ci, nombres, apellidos = parts
                        DATA_LEGACY.append({'ci': ci, 'nombres': nombres, 'apellidos': apellidos})
            print(f"Datos cargados exitosamente desde {filename}. Total de entradas legacy hasta ahora: {len(DATA_LEGACY)}")
        except FileNotFoundError:
            print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista.")
        except Exception as e:
            print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")
    if not DATA_LEGACY:
        print("Error: No se cargaron datos de ningún archivo legacy. Asegúrate de que los archivos existan y contengan datos.")

# Funciones de búsqueda para DATA_NEW (con campos adicionales)
def buscar_ci_new(ci_to_search):
    for entry in DATA_NEW:
        if entry['ci'] == ci_to_search:
            return entry
    return None

def buscar_por_nombres_new(nombres_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    for entry in DATA_NEW:
        if nombres_to_search_lower in unidecode(entry['nombres'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_apellidos_new(apellido_to_search):
    coincidencias = []
    apellido_to_search_lower = unidecode(apellido_to_search.lower())
    for entry in DATA_NEW:
        if apellido_to_search_lower in unidecode(entry['apellidos'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_nombres_y_apellidos_new(nombres_to_search, apellidos_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    apellidos_to_search_lower = unidecode(apellidos_to_search.lower())
    for entry in DATA_NEW:
        if (nombres_to_search_lower in unidecode(entry['nombres'].lower()) and
            apellidos_to_search_lower in unidecode(entry['apellidos'].lower())):
            coincidencias.append(entry)
    return coincidencias

# Funciones de búsqueda para DATA_LEGACY (sin campos adicionales)
def buscar_ci_legacy(ci_to_search):
    for entry in DATA_LEGACY:
        if entry['ci'] == ci_to_search:
            return entry
    return None

def buscar_por_nombres_legacy(nombres_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    for entry in DATA_LEGACY:
        if nombres_to_search_lower in unidecode(entry['nombres'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_apellidos_legacy(apellido_to_search):
    coincidencias = []
    apellido_to_search_lower = unidecode(apellido_to_search.lower())
    for entry in DATA_LEGACY:
        if apellido_to_search_lower in unidecode(entry['apellidos'].lower()):
            coincidencias.append(entry)
    return coincidencias

def buscar_por_nombres_y_apellidos_legacy(nombres_to_search, apellidos_to_search):
    coincidencias = []
    nombres_to_search_lower = unidecode(nombres_to_search.lower())
    apellidos_to_search_lower = unidecode(apellidos_to_search.lower())
    for entry in DATA_LEGACY:
        if (nombres_to_search_lower in unidecode(entry['nombres'].lower()) and
            apellidos_to_search_lower in unidecode(entry['apellidos'].lower())):
            coincidencias.append(entry)
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

    # PRIORIDAD 1: Buscar en DATA_NEW (resultados_cedulas.csv)
    if cedula:
        result = buscar_ci_new(cedula)
        if result:
            results = [result]
            search_type = "Cédula (Nuevo Archivo)"
    elif nombre and apellido:
        results = buscar_por_nombres_y_apellidos_new(nombre, apellido)
        search_type = "Nombre y Apellido (Nuevo Archivo)"
    elif nombre:
        results = buscar_por_nombres_new(nombre)
        search_type = "Nombre (Nuevo Archivo)"
    elif apellido:
        results = buscar_por_apellidos_new(apellido)
        search_type = "Apellido (Nuevo Archivo)"

    # Si no se encontraron resultados en DATA_NEW, buscar en DATA_LEGACY
    if not results:
        if cedula:
            result = buscar_ci_legacy(cedula)
            if result:
                results = [result]
                search_type = "Cédula (Archivos Antiguos)"
        elif nombre and apellido:
            results = buscar_por_nombres_y_apellidos_legacy(nombre, apellido)
            search_type = "Nombre y Apellido (Archivos Antiguos)"
        elif nombre:
            results = buscar_por_nombres_legacy(nombre)
            search_type = "Nombre (Archivos Antiguos)"
        elif apellido:
            results = buscar_por_apellidos_legacy(apellido)
            search_type = "Apellido (Archivos Antiguos)"

    return jsonify({'results': results, 'search_type': search_type})

# Ruta API para verificar el estado del servidor (si los datos están cargados)
@app.route('/status', methods=['GET'])
def status():
    if DATA_NEW or DATA_LEGACY:
        return jsonify({'status': 'ready', 'message': f'Datos cargados: {len(DATA_NEW)} (nuevo) + {len(DATA_LEGACY)} (antiguo) entradas'})
    else:
        return jsonify({'status': 'loading', 'message': 'Datos aún no cargados o archivo(s) no encontrado(s)'})

if __name__ == '__main__':
    load_new_data() # Carga los datos del nuevo archivo primero
    load_legacy_data(filenames=['cedulas_1.txt', 'cedulas_2.txt']) # Luego carga los archivos legacy
    app.run(debug=True, port=5000) # Ejecuta el servidor en el puerto 5000
