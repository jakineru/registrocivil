from flask import Flask, request, jsonify
from unidecode import unidecode
from flask_cors import CORS # Necesario para permitir solicitudes desde el navegador

app = Flask(__name__)
CORS(app) # Habilita CORS para todas las rutas

DATA = [] # Variable global para almacenar los datos cargados

# Función para cargar los datos desde múltiples archivos
def load_data(filenames=['cedulas_1.txt', 'cedulas_2.txt']):
    global DATA
    DATA = [] # Limpiar datos existentes antes de cargar
    for filename in filenames:
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                for line in file:
                    parts = line.strip().split(',')
                    if len(parts) == 3:
                        ci, nombres, apellidos = parts
                        DATA.append({'ci': ci, 'nombres': nombres, 'apellidos': apellidos})
            print(f"Datos cargados exitosamente desde {filename}. Total de entradas hasta ahora: {len(DATA)}")
        except FileNotFoundError:
            print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista.")
        except Exception as e:
            print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")
    if not DATA:
        print("Error: No se cargaron datos de ningún archivo. Asegúrate de que los archivos existan y contengan datos.")

# Funciones de búsqueda (sin cambios, operan sobre DATA combinada)
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
    for entry in DATA:
        if (nombres_to_search_lower in unidecode(entry['nombres'].lower()) and
            apellidos_to_search_lower in unidecode(entry['apellidos'].lower())):
            coincidencias.append(entry)
    return coincidencias

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    nombre = data.get('nombre', '').strip()
    apellido = data.get('apellido', '').strip()
    cedula = data.get('cedula', '').strip()

    results = []
    search_type = "No se realizó búsqueda"

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

@app.route('/status', methods=['GET'])
def status():
    if DATA:
        return jsonify({'status': 'ready', 'message': f'Datos cargados: {len(DATA)} entradas'})
    else:
        return jsonify({'status': 'loading', 'message': 'Datos aún no cargados o archivo(s) no encontrado(s)'})

if __name__ == '__main__':
    load_data(filenames=['cedulas_1.txt', 'cedulas_2.txt'])
    app.run(host='0.0.0.0', debug=True, port=5000)

