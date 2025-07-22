from flask import Flask, request, jsonify
from unidecode import unidecode
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, ElementClickInterceptedException, StaleElementReferenceException
import time
import os
import csv
import threading
import shutil
import tempfile
import random
import string
import traceback # Importar para obtener el stack trace
import requests

app = Flask(__name__)
CORS(app)

DATA = []
DATA_BY_CI = {}
LUGARES_MAP = {}
NAMES_WORD_INDEX = {}
APELLIDOS_WORD_INDEX = {}

QA_FILENAME = "preguntas_seguridad.txt"
qa_pairs = {}

webdriver_lock = threading.Lock()

# Número máximo de reintentos para cada operación crítica en search_dgrec
MAX_RETRIES = 2

# --- Funciones Auxiliares para Carga y Mapeo ---

def add_to_index(index_map, word, ci):
    normalized_word = unidecode(word.lower())
    if normalized_word:
        if normalized_word not in index_map:
            index_map[normalized_word] = set()
        index_map[normalized_word].add(ci)

def format_lugar_nacimiento(lugar_nacimiento_raw):
    lugar_nacimiento_stripped = lugar_nacimiento_raw.strip()
    if lugar_nacimiento_stripped in LUGARES_MAP:
        localidad = LUGARES_MAP[lugar_nacimiento_stripped]
        departamento_code = lugar_nacimiento_stripped
        return f"{localidad} ({departamento_code})"
    elif ',' in lugar_nacimiento_raw:
        lugar_parts = lugar_nacimiento_raw.split(',', 1)
        if len(lugar_parts) == 2:
            localidad = lugar_parts[1].strip()
            departamento = lugar_parts[0].strip()
            return f"{localidad} ({departamento})"
    return lugar_nacimiento_stripped

def load_qa_pairs(filename=QA_FILENAME):
    """Carga preguntas y respuestas desde un archivo."""
    global qa_pairs
    qa_pairs = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    question, answer = line.split("|", 1)
                    qa_pairs[question.strip()] = answer.strip()
        print(f"Cargadas {len(qa_pairs)} Q&A de '{filename}'.")
        print(f"DEBUG: Contenido de qa_pairs: {qa_pairs}")
    except FileNotFoundError:
        print(f"Advertencia: '{filename}' no encontrado. El CAPTCHA no se resolverá automáticamente.")
    except Exception as e:
        print(f"Error al cargar Q&A de '{filename}': {e}")

def generate_random_url():
    """
    Genera una URL con el formato especificado:
    https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid=x1:x2
    donde x1 es alfanumérico de 39 caracteres con un guion bajo o guion en una posición aleatoria,
    y x2 es un número del 0 al 9.
    """
    base_url = "https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid="
    
    chars = string.ascii_letters + string.digits
    special_chars = "_-"
    
    alphanum_part = ''.join(random.choice(chars) for _ in range(38))
    
    special_char = random.choice(special_chars)
    
    insert_pos = random.randint(0, 38)
    
    x1_list = list(alphanum_part)
    x1_list.insert(insert_pos, special_char)
    x1_val = ''.join(x1_list)
    
    x2_val = str(random.randint(0, 9))
    
    return f"{base_url}{x1_val}:{x2_val}"

def wait_for_document_complete(driver, timeout=10): 
    """Espera hasta que el document.readyState sea 'complete'."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print(f"DEBUG: Documento listo en {timeout}s.")
        return True
    except TimeoutException: 
        print(f"DEBUG: Timeout: Documento no cargó en {timeout}s.")
        return False
    except Exception as e: 
        print(f"DEBUG: Error en espera de documento: {e}")
        return False

def extract_question_from_page(driver):
    """Extrae la pregunta de seguridad."""
    try:
        print("DEBUG: Intentando extraer pregunta del CAPTCHA...")
        question_element = WebDriverWait(driver, 7).until( 
            EC.visibility_of_element_located((By.XPATH, "//*[contains(@class, 'captcha-pregunta')]//label | //label[contains(text(), '¿Cuál es') or contains(text(), '¿Cuántos') or contains(text(), '¿Qué número') or contains(text(), '¿Qué día')]"))
        )
        question_text = question_element.text.strip()
        print(f"DEBUG: Pregunta extraída: '{question_text}'.")
        return question_text
    except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
        print(f"DEBUG: Error al extraer pregunta: {type(e).__name__}. Contenido de la página (inicio): {driver.page_source[:500]}...")
        raise 
    except Exception as e:
        print(f"DEBUG: Error inesperado al extraer pregunta: {e}. Contenido de la página (inicio): {driver.page_source[:500]}...")
        raise

def check_for_permanence_error(driver):
    """Verifica el error de 'tiempo de permanencia'."""
    try:
        error_element = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'El tiempo de permanencia en el paso actual no puede superar los dos minutos')]"))
        )
        if error_element: 
            print("DEBUG: ¡Error de 'tiempo de permanencia' detectado!")
            return True
    except (TimeoutException, NoSuchElementException): 
        return False
    except Exception as e: 
        print(f"DEBUG: Error en verificación de permanencia: {e}")
        return False
    return False

def extract_page_data(driver, cedula):
    """Extrae información de la página de resultados."""
    data = {
        "ci": cedula,
        "nombres": "",
        "apellidos": "",
        "fecha_nacimiento": "",
        "lugar_nacimiento": ""
    }
    try:
        message_div = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-messages-warn')]"))
        )
        
        list_items = message_div.find_elements(By.TAG_NAME, "li")
        
        for item in list_items:
            text = item.text.strip()
            if "Nombres:" in text:
                data["nombres"] = text.replace("Nombres:", "").strip()
            elif "Apellidos:" in text:
                data["apellidos"] = text.replace("Apellidos:", "").strip()
            elif "Fecha de Nacimiento o Inscripción:" in text:
                data["fecha_nacimiento"] = text.replace("Fecha de Nacimiento o Inscripción:", "").strip()
            elif "Sección Judicial:" in text:
                data["lugar_nacimiento"] = text.replace("Sección Judicial:", "").strip()
        
        print(f"DEBUG: Datos extraídos para cédula {cedula}: {data}.")
        return data

    except TimeoutException: 
        print(f"DEBUG: Timeout: No se encontró div de resultados para cédula {cedula}.")
        return data
    except Exception as e: 
        print(f"DEBUG: Error al extraer datos para cédula {cedula}: {e}")
        return data

# --- Carga de Datos Inicial ---

def load_data(data_filenames=['cedulas_1.txt', 'cedulas_2.txt', 'resultados_cedulas.csv'], lugares_filename='lugares.txt'):
    global DATA, DATA_BY_CI, LUGARES_MAP, NAMES_WORD_INDEX, APELLIDOS_WORD_INDEX
    
    temp_data = {}
    NAMES_WORD_INDEX = {}
    APELLIDOS_WORD_INDEX = {}
    LUGARES_MAP = {}

    print("\n--- Iniciando carga de datos ---")

    load_qa_pairs(QA_FILENAME) # Cargar QA pairs (para CAPTCHA)

    print(f"Procesando archivo de lugares: {lugares_filename}")
    try:
        with open(lugares_filename, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                parts = line.strip().split(',', 1)
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

    for filename in data_filenames:
        print(f"Procesando archivo: {filename}")
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    parts = line.strip().split(',')
                    ci = None
                    current_entry = {}

                    if len(parts) == 3:
                        ci, nombres, apellidos = parts
                        current_entry = {'ci': ci, 'nombres': nombres, 'apellidos': apellidos}
                    elif len(parts) == 5:
                        ci, nombres, apellidos, fecha_nacimiento, lugar_nacimiento_raw = parts
                        current_entry = {
                            'ci': ci,
                            'nombres': nombres,
                            'apellidos': apellidos,
                            'fecha_nacimiento': fecha_nacimiento,
                            'lugar_nacimiento': format_lugar_nacimiento(lugar_nacimiento_raw)
                        }
                    else:
                        print(f"Advertencia: Línea {line_num} con formato inesperado en {filename}: '{line.strip()}'")
                        continue

                    if ci:
                        if ci in temp_data:
                            existing_entry = temp_data[ci]
                            # Lógica mejorada para priorizar entradas más completas.
                            # Si la entrada actual es más completa que la existente, la reemplaza.
                            # La "completeness" se basa en la cantidad de campos, priorizando 5 campos sobre 3.
                            # Nota: si una entrada DGREC de 5 campos se carga desde resultados_cedulas.csv y ya tiene 'source',
                            # tendrá 6 campos, lo que la hace "más completa" que una de 5 sin 'source'. Esto es deseable.
                            if len(current_entry) > len(existing_entry):
                                temp_data[ci] = current_entry
                            # Si ambas entradas tienen la misma cantidad de campos,
                            # la entrada del archivo actual (que es posterior en la lista data_filenames) gana.
                            elif len(current_entry) == len(existing_entry):
                                temp_data[ci] = current_entry
                            # Si la entrada actual es menos completa, se mantiene la existente.
                        else:
                            temp_data[ci] = current_entry
            print(f"Datos procesados desde {filename}. Entradas únicas en temp_data: {len(temp_data)}")
        except FileNotFoundError:
            print(f"Advertencia: {filename} no encontrado. Asegúrate de que exista.")
        except Exception as e:
            print(f"Ocurrió un error al cargar los datos desde {filename}: {e}")
    
    DATA = list(temp_data.values())
    DATA_BY_CI = {entry['ci']: entry for entry in DATA}

    # Nuevo mensaje de depuración para entradas completas cargadas
    # Se considera completa si tiene 'fecha_nacimiento' y 'lugar_nacimiento' (los campos adicionales)
    complete_entries_loaded = sum(1 for entry in DATA if 'fecha_nacimiento' in entry and 'lugar_nacimiento' in entry)
    print(f"DEBUG: {complete_entries_loaded} entradas completas (con fecha y lugar de nacimiento) cargadas en memoria al inicio.")

    print("\n--- Construyendo índices de nombres y apellidos ---")
    for entry in DATA:
        ci = entry['ci']
        nombres_words = unidecode(entry['nombres'].lower()).split()
        for word in nombres_words:
            add_to_index(NAMES_WORD_INDEX, word, ci)
        apellidos_words = unidecode(entry['apellidos'].lower()).split()
        for word in apellidos_words:
            add_to_index(APELLIDOS_WORD_INDEX, word, ci)
    
    if not DATA:
        print("Error: No se cargaron datos de ningún archivo.")
    else:
        print(f"\n--- Carga de datos finalizada ---")
        print(f"Total de entradas únicas y priorizadas en DATA (lista): {len(DATA)}")
        print(f"Total de entradas en DATA_BY_CI (diccionario): {len(DATA_BY_CI)}")
        print(f"Total de palabras indexadas en Nombres: {len(NAMES_WORD_INDEX)}")
        print(f"Total de palabras indexadas en Apellidos: {len(APELLIDOS_WORD_INDEX)}")

# --- Funciones de Búsqueda ---

def buscar_ci(ci_to_search):
    result = DATA_BY_CI.get(ci_to_search)
    print(f"DEBUG: buscar_ci para {ci_to_search} encontró en memoria: {result}")
    return result

def buscar_por_nombres(nombres_to_search):
    coincidencias_cis = set()
    nombres_search_words = unidecode(nombres_to_search.lower()).split()
    if not nombres_search_words: return []
    
    first_word = nombres_search_words[0]
    coincidencias_cis = NAMES_WORD_INDEX.get(first_word, set()).copy()
    for i in range(1, len(nombres_search_words)):
        word = nombres_search_words[i]
        coincidencias_cis.intersection_update(NAMES_WORD_INDEX.get(word, set()))
        if not coincidencias_cis: break
    
    return [DATA_BY_CI[ci] for ci in coincidencias_cis if ci in DATA_BY_CI]

def buscar_por_apellidos(apellido_to_search):
    coincidencias_cis = set()
    apellidos_search_words = unidecode(apellido_to_search.lower()).split()
    if not apellidos_search_words: return []

    first_word = apellidos_search_words[0]
    coincidencias_cis = APELLIDOS_WORD_INDEX.get(first_word, set()).copy()
    for i in range(1, len(apellidos_search_words)):
        word = apellidos_search_words[i]
        coincidencias_cis.intersection_update(APELLIDOS_WORD_INDEX.get(word, set()))
        if not coincidencias_cis: break
            
    return [DATA_BY_CI[ci] for ci in coincidencias_cis if ci in DATA_BY_CI]

def buscar_por_nombres_y_apellidos(nombres_to_search, apellidos_to_search):
    nombres_search_words = unidecode(nombres_to_search.lower()).split()
    apellidos_search_words = unidecode(apellidos_to_search.lower()).split()

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

    if nombres_search_words and apellidos_search_words:
        final_matching_cis = cis_from_names.intersection(cis_from_apellidos)
    elif nombres_search_words:
        final_matching_cis = cis_from_names
    elif apellidos_search_words:
        final_matching_cis = cis_from_apellidos
    else:
        final_matching_cis = set()

    return [DATA_BY_CI[ci] for ci in final_matching_cis if ci in DATA_BY_CI]

# --- Integración con DGREC (Webdriver) ---

def search_dgrec(ci):
    print(f"Iniciando búsqueda DGREC para CI: {ci}...")
    driver = None
    user_data_dir = None
    
    # Bucle de reintentos para la misma cédula
    for attempt in range(MAX_RETRIES):
        print(f"Intento {attempt + 1}/{MAX_RETRIES} para CI: {ci}")
        try:
            with webdriver_lock: # Asegura que solo una instancia de WebDriver se ejecute a la vez
                options = Options()
                # options.add_argument('--headless') # Comentado para depuración visual
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument("--disable-gpu")
                options.add_argument("--window-size=1920,1080")
                options.add_argument("--disable-extensions")
                options.add_argument("--disable-infobars")
                options.add_argument("--disable-browser-side-navigation")
                options.add_argument("--disable-features=VizDisplayCompositor")
                options.add_argument("--disable-popup-blocking")
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
                options.add_argument(f"user-agent={user_agent}")
                
                # --- Opciones anti-detección de scrap.py ---
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
                # --- Fin opciones anti-detección ---

                user_data_dir = tempfile.mkdtemp()
                options.add_argument(f"--user-data-dir={user_data_dir}")
                print(f"WebDriver user data dir: {user_data_dir}")
                
                # --- Configuración del ChromeDriver ---
                # DESCOMENTA Y AJUSTA LA SIGUIENTE LÍNEA SI CHROME NO SE DETECTA AUTOMÁTICAMENTE
                # options.binary_location = "C:/Program Files/Google/Chrome/Application/chrome.exe" 

                try:
                    print("DEBUG: Intentando instalar ChromeDriver con ChromeDriverManager()...")
                    driver_path = ChromeDriverManager().install()
                    print(f"DEBUG: ChromeDriver descargado/encontrado en: {driver_path}")
                    service = Service(driver_path)
                    
                    print("DEBUG: Intentando inicializar webdriver.Chrome()...")
                    driver = webdriver.Chrome(service=service, options=options)
                    print(f"DEBUG: WebDriver iniciado exitosamente para CI: {ci}")
                except Exception as e:
                    print(f"ERROR: Fallo CRÍTICO al iniciar WebDriver para CI {ci}: {type(e).__name__} - {e}")
                    print("ERROR: Esto suele indicar un problema con la instalación de Chrome, ChromeDriver o las dependencias de Selenium.")
                    print("ERROR: Asegúrate de que la ruta en 'options.binary_location' sea correcta o que Chrome esté en una ubicación estándar.")
                    print("ERROR: También, intenta limpiar la caché de webdriver_manager y reinstalar las dependencias.")
                    raise # Lanzar para que el bloque except del intento lo capture y reintente

                print(f"DEBUG: URL actual antes de navegar: {driver.current_url}")

                current_url = generate_random_url()
                
                # --- Lógica de interacción de página con reintento y recarga ---
                page_interaction_success = False
                for page_attempt in range(2): # Permitir 1 recarga/reintento para la secuencia inicial
                    try:
                        if page_attempt == 0:
                            driver.get(current_url) # Navegación inicial
                            print(f"DEBUG: Navegando a URL generada (intento 1): {current_url}")
                            time.sleep(random.uniform(0.3, 0.7)) # Pausa inicial
                            driver.refresh() # Forzar una recarga inicial
                            print(f"DEBUG: Forzando recarga de página (intento 1). URL: {driver.current_url}")
                            time.sleep(random.uniform(0.5, 1.0)) # Pausa después de la recarga
                        else:
                            driver.refresh() # Forzar una recarga para intentos subsiguientes
                            print(f"DEBUG: Forzando recarga de página (intento {page_attempt + 1}). URL: {driver.current_url}")
                            time.sleep(random.uniform(0.5, 1.0)) # Pausa después de la recarga

                        print(f"DEBUG: URL después de get/refresh: {driver.current_url}")
                        print(f"DEBUG: Contenido de la página (después de get/refresh, primeros 500 chars): {driver.page_source[:500]}...")

                        if not wait_for_document_complete(driver, 5): # Reducido a 5s
                            raise TimeoutException("Página inicial no cargada completamente.")

                        if check_for_permanence_error(driver):
                            raise WebDriverException("Error de tiempo de permanencia detectado en la página inicial.")

                        # Manejar el consentimiento si aparece (botón "No, gracias")
                        try:
                            print("DEBUG: Intentando encontrar botón de consentimiento...")
                            consent_button = WebDriverWait(driver, 2).until( # Reducido a 2s
                                EC.element_to_be_clickable((By.ID, "formTitulo:consentimientoView:b_nie:0"))
                            )
                            consent_button.click()
                            print(f"Consentimiento aceptado.")
                            time.sleep(random.uniform(0.1, 0.3)) # Pausa más corta
                            print(f"DEBUG: URL después de aceptar consentimiento: {driver.current_url}")
                        except TimeoutException:
                            print(f"No se encontró el botón de consentimiento o ya se aceptó.")
                        except ElementClickInterceptedException:
                            print(f"Clic en consentimiento interceptado, reintentando...")
                            time.sleep(0.1) # Pausa más corta
                            consent_button = WebDriverWait(driver, 2).until( # Reducido a 2s
                                EC.element_to_be_clickable((By.ID, "formTitulo:consentimientoView:b_nie:0"))
                            )
                            consent_button.click()
                            print(f"Consentimiento aceptado (reintento).")
                            time.sleep(random.uniform(0.1, 0.3)) # Pausa más corta
                            print(f"DEBUG: URL después de aceptar consentimiento (reintento): {driver.current_url}")

                        print("DEBUG: Esperando botón 'Siguiente' del formulario principal...")
                        next_button_initial = WebDriverWait(driver, 3).until( 
                            EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next"))
                        )
                        next_button_initial.click()
                        print("DEBUG: Clic en botón 'Siguiente' inicial.")
                        time.sleep(random.uniform(0.1, 0.3)) # Pausa más corta

                        if not wait_for_document_complete(driver, 5): # Reducido a 5s
                            raise TimeoutException("Página de CAPTCHA/datos no cargada completamente.")

                        if check_for_permanence_error(driver):
                            raise WebDriverException("Error de tiempo de permanencia detectado en la página de CAPTCHA/datos.")

                        print("DEBUG: Intentando resolver CAPTCHA...")
                        question_text = extract_question_from_page(driver) 
                        answer = qa_pairs.get(question_text)
                        if answer:
                            answer_input = WebDriverWait(driver, 2).until(EC.visibility_of_element_located((By.ID, "formTitulo:busquedaView:respuesta"))) # Reducido a 2s
                            answer_input.send_keys(answer)
                            print(f"DEBUG: Respuesta captcha ingresada para pregunta: '{question_text}'.")
                            page_interaction_success = True
                            break # Éxito en la interacción, salir del bucle de page_interaction_attempts
                        else:
                            print(f"DEBUG: No se encontró respuesta para la pregunta: '{question_text}'. `qa_pairs` contiene: {qa_pairs}.")
                            raise ValueError("Respuesta captcha no encontrada o pregunta inesperada.")

                    except (TimeoutException, NoSuchElementException, ElementClickInterceptedException, ValueError, WebDriverException) as e_page_interaction:
                        print(f"DEBUG: Fallo en la secuencia de interacción de página (Intento {page_attempt + 1} de página): {type(e_page_interaction).__name__}. Mensaje: {e_page_interaction}. URL: {driver.current_url}")
                        if page_attempt == 0: # Si el primer intento falla, el siguiente intento forzará una recarga.
                            print("DEBUG: Primer intento de interacción falló. El siguiente intento forzará una recarga.")
                        else:
                            # Si el segundo intento (después de recargar) también falla, relanzar para activar el reintento externo.
                            raise e_page_interaction 
                
                if not page_interaction_success:
                    raise WebDriverException("Fallo en la secuencia de interacción de página después de reintentos internos.")
                # --- Fin Lógica de interacción de página con reintento y recarga ---

                time.sleep(random.uniform(0.2, 0.5)) # Pausa después del CAPTCHA

                print("DEBUG: Intentando encontrar campo de CI... (después de CAPTCHA)")
                ci_input = WebDriverWait(driver, 3).until(EC.visibility_of_element_located((By.ID, "formTitulo:busquedaView:tabs:nroDocumento"))) # Reducido a 3s
                ci_input.clear()
                ci_input.send_keys(ci)
                print(f"DEBUG: CI {ci} ingresada.")
                time.sleep(random.uniform(0.2, 0.5)) # Pausa más corta

                print("DEBUG: Intentando encontrar botón de búsqueda (mismo ID que 'Siguiente')... (después de CI)")
                search_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next"))) # Reducido a 3s
                search_button.click()
                print(f"DEBUG: Botón de búsqueda clicado.")
                print(f"DEBUG: URL después de clic en búsqueda: {driver.current_url}")
                time.sleep(random.uniform(0.5, 1.0)) # Pausa después de búsqueda

                if not wait_for_document_complete(driver, 10):
                    raise TimeoutException("Página de resultados finales no cargada completamente.")

                if check_for_permanence_error(driver):
                    raise WebDriverException("Error de tiempo de permanencia detectado en la página de resultados.")

                print("DEBUG: Esperando elemento de respuesta final (ui-messages-warn)...")
                response_element = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-messages-warn')]"))
                )
                print(f"DEBUG: Elemento de resultados (ui-messages-warn) encontrado. URL final: {driver.current_url}")

                extracted_data = extract_page_data(driver, ci)
                if extracted_data and extracted_data.get('nombres'):
                    extracted_data['lugar_nacimiento'] = format_lugar_nacimiento(extracted_data['lugar_nacimiento'])
                    # Asegurarse de que todos los campos esperados por el CSV estén presentes
                    for field in ['nombres', 'apellidos', 'fecha_nacimiento', 'lugar_nacimiento']:
                        if field not in extracted_data:
                            extracted_data[field] = "" # Inicializar con cadena vacía si falta
                    # Añadir una fuente para el frontend
                    extracted_data['source'] = 'dgrec_success'
                    return extracted_data
                else:
                    print(f"DGREC: CI {ci} no encontrada o datos incompletos en la respuesta.")
                    return None

        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException, ValueError, WebDriverException) as e:
            print(f"DGREC ERROR (Intento {attempt + 1}): Fallo en CI {ci}. Tipo: {type(e).__name__}, Mensaje: {e}")
            print(f"DEBUG: URL actual: {driver.current_url if driver else 'N/A'}")
            print(f"DEBUG: Contenido actual de la página (primeros 500 chars): {driver.page_source[:500] if driver else 'N/A'}...")
            
            # Limpiar y cerrar WebDriver para el reintento
            if driver:
                try:
                    driver.quit()
                    print(f"WebDriver cerrado para reintento de CI: {ci}")
                except Exception as ex_quit:
                    print(f"Error al cerrar WebDriver para reintento de CI {ci}: {ex_quit}")
            if user_data_dir and os.path.exists(user_data_dir):
                time.sleep(0.1) # Pequeña pausa antes de intentar la eliminación
                try:
                    shutil.rmtree(user_data_dir)
                    print(f"Directorio temporal eliminado para reintento: {user_data_dir}")
                except PermissionError as pe:
                    print(f"Error de permiso al eliminar dir temporal {user_data_dir}: {pe}. Reintenta cerrar Chrome manualmente.")
                except OSError as ose:
                    print(f"Error al eliminar dir temporal {user_data_dir}: {ose}.")
                except Exception as generic_e:
                    print(f"Error inesperado al eliminar dir temporal {user_data_dir}: {generic_e}.")
            
            if attempt < MAX_RETRIES - 1:
                print(f"Reintentando CI {ci}...")
                time.sleep(random.uniform(1, 2)) # Pausa antes del siguiente intento (reducida)
            else:
                print(f"CI {ci} falló después de {MAX_RETRIES} intentos.")
                return None # Todos los reintentos fallaron
        except Exception as e:
            print(f"DGREC ERROR (General - Intento {attempt + 1}): Error inesperado al buscar en DGREC para CI {ci}: {e}")
            print(f"DEBUG: URL actual: {driver.current_url if driver else 'N/A'}")
            print(f"DEBUG: Contenido actual de la página (primeros 500 chars): {driver.page_source[:500] if driver else 'N/A'}...")
            
            if driver:
                try:
                    driver.quit()
                    print(f"WebDriver cerrado para CI: {ci}")
                except Exception as ex_quit:
                    print(f"Error al cerrar WebDriver para CI {ci}: {ex_quit}")
            if user_data_dir and os.path.exists(user_data_dir):
                time.sleep(0.1) 
                try:
                    shutil.rmtree(user_data_dir)
                    print(f"Directorio temporal eliminado: {user_data_dir}")
                except PermissionError as pe:
                    print(f"Error de permiso al eliminar dir temporal {user_data_dir}: {pe}. Reintenta cerrar Chrome manualmente.")
                except OSError as ose:
                    print(f"Error al eliminar dir temporal {user_data_dir}: {ose}.")
                except Exception as generic_e:
                    print(f"Error inesperado al eliminar dir temporal {user_data_dir}: {generic_e}.")
            
            if attempt < MAX_RETRIES - 1:
                print(f"Reintentando CI {ci}...")
                time.sleep(random.uniform(1, 2)) # Pausa antes del siguiente intento (reducida)
            else:
                print(f"CI {ci} falló después de {MAX_RETRIES} intentos.")
                return None # Todos los reintentos fallaron
    return None # Si el bucle de reintentos termina sin éxito

# --- Funciones para Actualizar CSV ---
def append_to_csv(data_entry):
    filename = 'resultados_cedulas.csv'
    file_exists = os.path.isfile(filename)
    
    fieldnames = ['ci', 'nombres', 'apellidos', 'fecha_nacimiento', 'lugar_nacimiento']

    print(f"DEBUG: Intentando añadir/actualizar CI {data_entry.get('ci', 'N/A')} en {filename}.")
    print(f"DEBUG: Data a escribir: {data_entry}")

    try:
        # Asegurarse de que data_entry contenga todas las claves esperadas por fieldnames
        # Esto previene errores si algún campo no fue extraído por search_dgrec
        sanitized_data_entry = {key: data_entry.get(key, "") for key in fieldnames}

        with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists or os.stat(filename).st_size == 0:
                writer.writeheader()
                print(f"DEBUG: Cabecera escrita en {filename}.")
            writer.writerow(sanitized_data_entry) # Usar la entrada sanitizada
            print(f"DEBUG: Datos escritos para CI {sanitized_data_entry.get('ci', 'N/A')} en {filename}.")
        
        # Actualizar DATA_BY_CI y DATA en memoria con la entrada completa
        ci_val = data_entry['ci']
        print(f"DEBUG: Intentando actualizar datos en memoria para CI: {ci_val}")
        
        if ci_val in DATA_BY_CI:
            existing_entry = DATA_BY_CI[ci_val]
            print(f"DEBUG: Entrada existente en memoria para CI {ci_val}: {existing_entry}")
            # Solo actualiza si la nueva entrada es más completa o si la existente era incompleta
            # La "completitud" aquí se refiere a la presencia de fecha_nacimiento y lugar_nacimiento
            # O si la nueva entrada es simplemente más grande (ej. tiene el campo 'source')
            if ('fecha_nacimiento' in data_entry and 'lugar_nacimiento' in data_entry and 
                ('fecha_nacimiento' not in existing_entry or 'lugar_nacimiento' not in existing_entry)) or \
               (len(data_entry) > len(existing_entry)): # Para manejar el caso del campo 'source'
                
                DATA_BY_CI[ci_val] = data_entry
                # Actualizar la lista DATA también para consistencia
                for i, entry in enumerate(DATA):
                    if entry['ci'] == ci_val:
                        DATA[i] = data_entry
                        print(f"DEBUG: Entrada en lista DATA actualizada para CI: {ci_val}")
                        break
                print(f"DEBUG: Datos en memoria (DATA_BY_CI) actualizados para CI: {ci_val} a: {DATA_BY_CI[ci_val]}")
            else:
                print(f"DEBUG: Entrada en memoria para CI {ci_val} ya es igual o más completa. No se actualiza.")
        else:
            DATA_BY_CI[ci_val] = data_entry
            DATA.append(data_entry)
            print(f"DEBUG: Nueva entrada añadida a memoria (DATA_BY_CI y DATA) para CI: {ci_val}")

    except Exception as e:
        print(f"ERROR: Fallo CRÍTICO al añadir/actualizar CI {data_entry.get('ci', 'N/A')} en memoria o CSV: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")

# --- Rutas de la API ---

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    nombre = data.get('nombre', '').strip()
    apellido = data.get('apellido', '').strip()
    cedula = data.get('ci', '').strip() # Cambiado a 'ci' para coincidir con el frontend
    session_id = data.get('sessionId', 'N/A')
    user_ip = data.get('userIp', 'N/A')

    results = []
    search_type = "No se realizó búsqueda"
    
    print(f"🔍 {user_ip} ({session_id}) - Solicitud de búsqueda recibida.")

    if cedula:
        search_type = "Cédula"
        result_local = buscar_ci(cedula) # Primero busca localmente
        
        # Si la cédula ya está en memoria Y tiene los campos de una entrada completa (fecha y lugar de nacimiento)
        if result_local and 'fecha_nacimiento' in result_local and 'lugar_nacimiento' in result_local: 
            results = [result_local]
            # Asegurarse de que el 'source' sea 'local_complete' si no está presente o es diferente
            if 'source' not in results[0] or results[0]['source'] != 'local_complete':
                results[0]['source'] = 'local_complete'
            print(f"CI {cedula} encontrada localmente (completa).")
        else: # Si no está completa localmente, intenta DGREC
            print(f"CI {cedula} no completa localmente o no encontrada. Procesando DGREC...")
            dgrec_result = search_dgrec(cedula)
            if dgrec_result:
                print(f"DEBUG: search_dgrec devolvió datos. Llamando a append_to_csv para CI: {cedula}")
                results = [dgrec_result]
                append_to_csv(dgrec_result)
                print(f"CI {cedula} encontrada y añadida/actualizada desde DGREC.")
            else:
                # Si DGREC falla, intenta devolver el resultado local incompleto si existe
                if result_local:
                    results = [result_local]
                    results[0]['source'] = 'local_fallback' # Marcar como fallback para no mostrar lupa
                    print(f"CI {cedula} no encontrada en DGREC, devolviendo datos locales incompletos.")
                else:
                    print(f"CI {cedula} no encontrada en DGREC ni localmente.")
    elif nombre and apellido:
        search_type = "Nombre y Apellido"
        results = buscar_por_nombres_y_apellidos(nombre, apellido)
        # Añadir fuente 'local_complete' por defecto para búsquedas por nombre/apellido
        for r in results:
            if 'source' not in r: # Evitar sobreescribir si ya tiene source de DGREC
                r['source'] = 'local_complete'
    elif nombre:
        search_type = "Nombre"
        results = buscar_por_nombres(nombre)
        for r in results:
            if 'source' not in r:
                r['source'] = 'local_complete'
    elif apellido:
        search_type = "Apellido"
        results = buscar_por_apellidos(apellido)
        for r in results:
            if 'source' not in r:
                r['source'] = 'local_complete'

    return jsonify({'results': results, 'search_type': search_type})

@app.route('/status', methods=['GET'])
def status():
    if DATA:
        return jsonify({'status': 'ready', 'message': f'Datos cargados: {len(DATA)} entradas'})
    else:
        return jsonify({'status': 'loading', 'message': 'Datos aún no cargados o archivo(s) no encontrado(s)'})

@app.route('/dgrec_lookup', methods=['POST'])
def dgrec_lookup_endpoint():
    data = request.json
    ci = data.get('ci', '').strip()
    session_id = data.get('sessionId', 'N/A')
    user_ip = data.get('userIp', 'N/A')

    if not ci:
        return jsonify({'error': 'Cédula es requerida'}), 400

    local_result = buscar_ci(ci)
    # Si la cédula ya está en memoria Y tiene los campos de una entrada completa (fecha y lugar de nacimiento)
    if local_result and 'fecha_nacimiento' in local_result and 'lugar_nacimiento' in local_result:
        print(f"CI {ci} ya está completa en memoria. No se consulta DGREC.")
        # Asegurarse de que el 'source' sea 'local_complete' si no está presente o es diferente
        if 'source' not in local_result or local_result['source'] != 'local_complete':
            local_result['source'] = 'local_complete' 
        return jsonify({'result': local_result, 'source': 'local_complete'})

    print(f"⚡️ {user_ip} ({session_id}) - Solicitud DGREC para CI {ci} recibida.")
    dgrec_result = search_dgrec(ci)
    if dgrec_result:
        print(f"DEBUG: dgrec_lookup_endpoint recibió datos. Llamando a append_to_csv para CI: {ci}")
        append_to_csv(dgrec_result)
        print(f"✅ {user_ip} ({session_id}) - Cédula {ci} añadida/actualizada desde DGREC.")
        return jsonify({'result': dgrec_result, 'source': 'dgrec_success'})
    else:
        print(f"❌ {user_ip} ({session_id}) - Cédula {ci} no encontrada en DGREC o falló la consulta.")
        # Si DGREC falla en el endpoint dgrec_lookup, no hay fallback local aquí.
        # Esto es porque este endpoint se llama *después* de que ya se intentó la búsqueda local
        # y se encontró un resultado incompleto. Si DGREC falla aquí, significa que no se pudo completar.
        return jsonify({'result': None, 'source': 'dgrec_failed'})

if __name__ == '__main__':
    load_data(data_filenames=['cedulas_1.txt', 'cedulas_2.txt', 'resultados_cedulas.csv'], lugares_filename='lugares.txt')
    app.run(debug=True, port=5000)
