import time
import random
import shutil 
import tempfile 
import os 
import csv 
import threading 
import queue # Importar queue para la cola de cédulas
import concurrent.futures # Para ThreadPoolExecutor
from json.decoder import JSONDecodeError # Importar JSONDecodeError
from selenium.common.exceptions import WebDriverException # Importar WebDriverException
import string # Para generar caracteres aleatorios

# Nombres de archivos
CEDULAS_FILENAME = "cst.txt"
OUTPUT_CSV_FILENAME = "resultados_cedulas.csv"
QA_FILENAME = "preguntas_seguridad.txt"

# Número máximo de reintentos para cada operación crítica
MAX_RETRIES = 3 

# Global queue for cédulas to be deleted from file
processed_for_deletion_queue = queue.Queue()
# Lock for file write operations on CEDULAS_FILENAME
file_write_lock = threading.Lock()
# Event to signal the file writer thread to stop
stop_writer_event = threading.Event()

def load_qa_pairs(filename=QA_FILENAME):
    """Carga preguntas y respuestas desde un archivo."""
    qa_pairs = {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "|" in line:
                    question, answer = line.split("|", 1)
                    qa_pairs[question.strip()] = answer.strip()
        print(f"Cargadas {len(qa_pairs)} Q&A de '{filename}'.")
    except FileNotFoundError:
        print(f"Advertencia: '{filename}' no encontrado. Captcha no se resolverá.")
    except Exception as e:
        print(f"Error al cargar Q&A de '{filename}': {e}")
    return qa_pairs

def load_cedulas(filename=CEDULAS_FILENAME):
    """Carga cédulas desde un archivo."""
    cedulas = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                cedula = line.strip()
                if cedula:
                    cedulas.append(cedula)
        print(f"Cargadas {len(cedulas)} cédulas de '{filename}'.")
    except FileNotFoundError:
        print(f"Error: '{filename}' no encontrado. No hay cédulas.")
    except Exception as e:
        print(f"Error al cargar cédulas de '{filename}': {e}")
    return cedulas

def generate_random_url():
    """
    Genera una URL con el formato especificado:
    https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid=x1:x2
    donde x1 es alfanumérico de 39 caracteres con un guion bajo o guion en una posición aleatoria,
    y x2 es un número del 0 al 9.
    """
    base_url = "https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid="
    
    # Generar x1: 39 caracteres alfanuméricos con un '_'' o '-' en una posición aleatoria
    chars = string.ascii_letters + string.digits # a-z, A-Z, 0-9
    special_chars = "_-" # Caracteres especiales permitidos
    
    # Generar 38 caracteres alfanuméricos
    alphanum_part = ''.join(random.choice(chars) for _ in range(38))
    
    # Elegir un carácter especial aleatorio
    special_char = random.choice(special_chars)
    
    # Elegir una posición aleatoria (0 a 38) para insertar el carácter especial en x1
    insert_pos = random.randint(0, 38)
    
    # Construir x1
    x1_list = list(alphanum_part)
    x1_list.insert(insert_pos, special_char)
    x1_val = ''.join(x1_list)
    
    # Generar x2: un número del 0 al 9
    x2_val = str(random.randint(0, 9))
    
    return f"{base_url}{x1_val}:{x2_val}"


def wait_for_document_complete(driver, timeout=10): 
    """Espera hasta que el document.readyState sea 'complete'."""
    from selenium.webdriver.support.ui import WebDriverWait 
    from selenium.common.exceptions import TimeoutException 

    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print(f"Documento listo en {timeout}s.")
        return True
    except TimeoutException: 
        print(f"Timeout: Documento no cargó en {timeout}s.")
        return False
    except Exception as e: 
        print(f"Error en espera de documento: {e}")
        return False

def extract_question_from_page(driver):
    """Extrae la pregunta de seguridad."""
    from selenium.webdriver.support.ui import WebDriverWait 
    from selenium.webdriver.support import expected_conditions as EC 
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException 
    from selenium.webdriver.common.by import By 

    try:
        question_element = WebDriverWait(driver, 7).until(
            EC.visibility_of_element_located((By.XPATH, "//*[contains(@class, 'captcha-pregunta')]//label | //label[contains(text(), '¿Cuál es') or contains(text(), '¿Cuántos') or contains(text(), '¿Qué número') or contains(text(), '¿Qué día')]"))
        )
        question_text = question_element.text.strip()
        print(f"Pregunta extraída.")
        return question_text
    except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
        print(f"Error al extraer pregunta: {type(e).__name__}.")
        raise 
    except Exception as e:
        print(f"Error inesperado al extraer pregunta: {e}")
        raise

def check_for_permanence_error(driver):
    """Verifica el error de 'tiempo de permanencia'."""
    from selenium.webdriver.support.ui import WebDriverWait 
    from selenium.webdriver.support import expected_conditions as EC 
    from selenium.common.exceptions import TimeoutException, NoSuchElementException 
    from selenium.webdriver.common.by import By 

    try:
        error_element = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'El tiempo de permanencia en el paso actual no puede superar los dos minutos')]"))
        )
        if error_element: 
            print("¡Error de 'tiempo de permanencia' detectado!")
            return True
    except (TimeoutException, NoSuchElementException): 
        return False
    except Exception as e: 
        print(f"Error en verificación de permanencia: {e}")
        return False
    return False

def extract_page_data(driver, cedula):
    """Extrae información de la página de resultados."""
    from selenium.webdriver.support.ui import WebDriverWait 
    from selenium.webdriver.support import expected_conditions as EC 
    from selenium.common.exceptions import TimeoutException 
    from selenium.webdriver.common.by import By 

    data = {
        "cedula": cedula,
        "nombre": "",
        "apellido": "",
        "fecha_nacimiento": "",
        "seccion_judicial": ""
    }
    try:
        message_div = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'ui-messages-warn')]"))
        )
        
        list_items = message_div.find_elements(By.TAG_NAME, "li")
        
        for item in list_items:
            text = item.text.strip()
            if "Nombres:" in text:
                data["nombre"] = text.replace("Nombres:", "").strip()
            elif "Apellidos:" in text:
                data["apellido"] = text.replace("Apellidos:", "").strip()
            elif "Fecha de Nacimiento o Inscripción:" in text:
                data["fecha_nacimiento"] = text.replace("Fecha de Nacimiento o Inscripción:", "").strip()
            elif "Sección Judicial:" in text:
                data["seccion_judicial"] = text.replace("Sección Judicial:", "").strip()
        
        print(f"Datos extraídos para cédula {cedula}.")
        return data

    except TimeoutException: 
        print(f"Timeout: No se encontró div de resultados para cédula {cedula}.")
        return data
    except Exception as e: 
        print(f"Error al extraer datos para cédula {cedula}: {e}")
        return data

def file_writer_thread_function():
    """
    Hilo dedicado a escribir en el archivo de cédulas, procesando en lotes.
    """
    print("Hilo Escritor: Iniciado.")
    BATCH_SIZE = 50  # Procesar 50 cédulas a la vez
    TIMEOUT_SECONDS = 10  # O escribir cada 10 segundos si hay menos de BATCH_SIZE

    current_batch_to_delete = set()
    last_write_time = time.time()

    while not stop_writer_event.is_set() or not processed_for_deletion_queue.empty():
        try:
            # Obtener elementos de la cola sin bloquear indefinidamente
            cedula_to_delete = processed_for_deletion_queue.get(timeout=1)  # Pequeño timeout
            current_batch_to_delete.add(cedula_to_delete)
        except queue.Empty:
            pass  # No hay elementos en la cola, seguir verificando la señal de parada o el timeout

        # Verificar si se alcanzó el tamaño del lote o el tiempo de espera
        if (len(current_batch_to_delete) >= BATCH_SIZE or 
            (time.time() - last_write_time >= TIMEOUT_SECONDS and current_batch_to_delete)):
            
            with file_write_lock:
                print(f"Hilo Escritor: Procesando lote de {len(current_batch_to_delete)} cédulas para eliminación.")
                # Leer todas las líneas del archivo
                all_lines = []
                try:
                    with open(CEDULAS_FILENAME, "r", encoding="utf-8") as f_read:
                        all_lines = f_read.readlines()
                except FileNotFoundError:
                    print(f"Hilo Escritor: Advertencia, '{CEDULAS_FILENAME}' no encontrado durante la escritura.")
                    current_batch_to_delete.clear() # Limpiar lote ya que el archivo podría no existir
                    continue

                # Filtrar las cédulas del lote actual
                remaining_lines = []
                for line in all_lines:
                    if line.strip() not in current_batch_to_delete:
                        remaining_lines.append(line)
                
                # Volver a escribir las líneas restantes
                try:
                    with open(CEDULAS_FILENAME, "w", encoding="utf-8") as f_write:
                        f_write.writelines(remaining_lines)
                    print(f"Hilo Escritor: '{CEDULAS_FILENAME}' actualizado. Eliminadas {len(current_batch_to_delete)} cédulas.")
                except Exception as e:
                    print(f"Hilo Escritor: Error al reescribir '{CEDULAS_FILENAME}': {e}")
                
                current_batch_to_delete.clear()
                last_write_time = time.time()
        
        # Pequeña pausa para evitar el uso excesivo de CPU si la cola está vacía
        time.sleep(0.1)

    # Escritura final para asegurar que cualquier elemento restante en la cola sea procesado antes de salir
    if current_batch_to_delete:
        with file_write_lock:
            print(f"Hilo Escritor: Procesando lote final de {len(current_batch_to_delete)} cédulas para eliminación.")
            all_lines = []
            try:
                with open(CEDULAS_FILENAME, "r", encoding="utf-8") as f_read:
                    all_lines = f_read.readlines()
            except FileNotFoundError:
                print(f"Hilo Escritor: Advertencia, '{CEDULAS_FILENAME}' no encontrado durante la escritura final.")
            
            remaining_lines = []
            for line in all_lines:
                if line.strip() not in current_batch_to_delete:
                    remaining_lines.append(line)
            
            try:
                with open(CEDULAS_FILENAME, "w", encoding="utf-8") as f_write:
                    f_write.writelines(remaining_lines)
                print(f"Hilo Escritor: '{CEDULAS_FILENAME}' final actualizado. Eliminadas {len(current_batch_to_delete)} cédulas restantes.")
            except Exception as e:
                print(f"Hilo Escritor: Error al reescribir '{CEDULAS_FILENAME}' en la finalización: {e}")
    
    print("Hilo Escritor: Finalizado.")


def worker_thread_function(thread_id, qa_pairs, output_csv_filename, csv_lock, cedula_queue, processed_cedulas_set, processed_cedulas_lock):
    """Función que cada hilo ejecutará para procesar cédulas."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options 
    from selenium.webdriver.chrome.service import Service 
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException, ElementClickInterceptedException 
    from selenium.webdriver.common.by import By 

    print(f"Hilo {thread_id}: Iniciando.")

    chrome_options = Options()
    chrome_options.add_argument("--headless")  
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-browser-side-navigation")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--disable-popup-blocking")
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")

    while True:
        cedula_actual = None
        current_url = None

        try:
            cedula_actual = cedula_queue.get(block=False) 
            current_url = generate_random_url() # Generar la URL dinámicamente
            
            print(f"Hilo {thread_id}: Procesando Cédula: {cedula_actual} con URL generada: {current_url}.")

            # Flag para rastrear si la cédula fue procesada exitosamente después de los reintentos
            cedula_processed_successfully = False

            # Bucle externo para reintentar la *misma* cédula
            for cedula_attempt in range(MAX_RETRIES):
                driver = None # Reiniciar driver para cada intento
                user_data_dir = None # Reiniciar user_data_dir para cada intento

                try:
                    # Crear el directorio temporal en la ruta especificada
                    user_data_dir = tempfile.mkdtemp(dir='E:/temp') 
                    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")
                    print(f"Hilo {thread_id}: Dir temp: {user_data_dir} (Cédula {cedula_actual}, Intento {cedula_attempt + 1}).")

                    try:
                        # Intentar obtener el ChromeDriver con webdriver_manager (método preferido)
                        driver_path = None
                        try:
                            driver_path = ChromeDriverManager().install()
                            print(f"Hilo {thread_id}: ChromeDriver obtenido con webdriver_manager.")
                        except Exception as driver_manager_e:
                            print(f"Hilo {thread_id}: Error al obtener ChromeDriver con webdriver_manager: {driver_manager_e}.")
                            print(f"Hilo {thread_id}: Intentando iniciar WebDriver sin especificar ruta de driver (Chrome 125+).")
                            # Si webdriver_manager falla, no establecemos driver_path, Service() lo manejará.

                        if driver_path:
                            service = Service(driver_path)
                        else:
                            # Si webdriver_manager falló, o si Chrome 125+ está en uso,
                            # intentamos inicializar Service sin una ruta específica.
                            # Selenium debería encontrar el ChromeDriver integrado si chrome_options.binary_location está configurado
                            # o si Chrome está en una ubicación estándar.

                            # Si necesitas especificar la ruta de tu ejecutable de Chrome directamente (ej. "C:/Program Files/Google/Chrome/Application/chrome.exe"):
                            chrome_options.binary_location = "C:/Program Files/Google/Chrome/Application/chrome.exe" # <--- VERIFICA ESTA RUTA EN TU PC
                            service = Service() # Deja que Service intente encontrarlo automáticamente o use binary_location

                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        print(f"Hilo {thread_id}: WebDriver iniciado (Cédula {cedula_actual}, Intento {cedula_attempt + 1}).")
                    except (JSONDecodeError, WebDriverException) as init_e: # Captura JSONDecodeError y otros WebDriverExceptions
                        print(f"Hilo {thread_id}: Error al iniciar WebDriver para {cedula_actual}: {type(init_e).__name__} - {init_e}. Reintentando...")
                        if driver: # Asegurarse de cerrar si se abrió parcialmente
                            try:
                                driver.quit()
                            except Exception as ex_quit:
                                print(f"Hilo {thread_id}: Error al cerrar WebDriver tras fallo de inicio: {ex_quit}.")
                        if user_data_dir: # Asegurarse de limpiar el dir temporal
                            time.sleep(0.5) 
                            try:
                                shutil.rmtree(user_data_dir)
                            except OSError as os_e:
                                print(f"Hilo {thread_id}: Error al eliminar dir temporal '{user_data_dir}': {os_e}.")
                            except Exception as generic_e:
                                print(f"Hilo {thread_id}: Error inesperado al eliminar dir temporal '{user_data_dir}': {generic_e}.")
                        time.sleep(random.uniform(1.0, 3.0)) # Pequeña pausa antes de reintentar el inicio
                        continue # Ir al siguiente intento del bucle para esta cédula
                    except Exception as init_e: # Captura cualquier otra excepción al iniciar WebDriver
                        print(f"Hilo {thread_id}: Error inesperado al iniciar WebDriver para {cedula_actual}: {type(init_e).__name__} - {init_e}. Reintentando...")
                        if driver:
                            try:
                                driver.quit()
                            except Exception as ex_quit:
                                print(f"Hilo {thread_id}: Error al cerrar WebDriver tras fallo inesperado: {ex_quit}.")
                        if user_data_dir:
                            time.sleep(0.5) 
                            try:
                                shutil.rmtree(user_data_dir)
                            except OSError as os_e:
                                print(f"Hilo {thread_id}: Error al eliminar dir temporal '{user_data_dir}': {os_e}.")
                            except Exception as generic_e:
                                print(f"Hilo {thread_id}: Error inesperado al eliminar dir temporal '{user_data_dir}': {generic_e}.")
                        time.sleep(random.uniform(1.0, 3.0)) # Pequeña pausa antes de reintentar el inicio
                        continue # Ir al siguiente intento del bucle para esta cédula


                    driver.get(current_url)
                    print(f"Hilo {thread_id}: Navegando a: {current_url}.")

                    time.sleep(random.uniform(0.5, 1.5))

                    if not wait_for_document_complete(driver, 10):
                        raise TimeoutException("Página inicial no cargada.")

                    if check_for_permanence_error(driver):
                        print(f"Hilo {thread_id}: Error de permanencia en inicio para {cedula_actual}. Reintentando...")
                        raise WebDriverException("Error de tiempo de permanencia.")

                    # Aceptar términos
                    accept_terms_radio = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "formTitulo:consentimientoView:b_nie:0")))
                    try:
                        if not accept_terms_radio.is_selected():
                            driver.execute_script("arguments[0].click();", accept_terms_radio)
                            print(f"Hilo {thread_id}: Clic en 'Acepto términos'.")
                    except ElementClickInterceptedException:
                        print(f"Hilo {thread_id}: Clic interceptado. JS para 'Acepto términos'.")
                        driver.execute_script("arguments[0].click();", accept_terms_radio)
                    time.sleep(random.uniform(0.5, 1.0))

                    # Clic en 'Siguiente' (después de aceptar términos)
                    next_button_terms = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next")))
                    try:
                        driver.execute_script("arguments[0].click();", next_button_terms)
                        print(f"Hilo {thread_id}: Clic en 'Siguiente' (términos).")
                    except ElementClickInterceptedException:
                        print(f"Hilo {thread_id}: Clic interceptado. JS para 'Siguiente'.")
                        driver.execute_script("arguments[0].click();", next_button_terms)
                    time.sleep(random.uniform(0.5, 1.0))

                    if not wait_for_document_complete(driver, 10):
                        raise TimeoutException("Página captcha no cargada.")

                    if check_for_permanence_error(driver):
                        print(f"Hilo {thread_id}: Error de permanencia en captcha para {cedula_actual}. Reintentando...")
                        raise WebDriverException("Error de tiempo de permanencia.")

                    # Resolver Captcha
                    question_text = extract_question_from_page(driver)
                    answer = qa_pairs.get(question_text)
                    if answer:
                        answer_input = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "formTitulo:busquedaView:respuesta")))
                        answer_input.send_keys(answer)
                        print(f"Hilo {thread_id}: Respuesta captcha ingresada.")
                    else:
                        print(f"Hilo {thread_id}: No se encontró respuesta para: '{question_text}'.")
                        raise ValueError("Respuesta captcha no encontrada.")
                    time.sleep(random.uniform(0.5, 1.0))

                    # Ingresar Cédula
                    cedula_input = WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "formTitulo:busquedaView:tabs:nroDocumento")))
                    cedula_input.send_keys(cedula_actual)
                    print(f"Hilo {thread_id}: Cédula ingresada: {cedula_actual}.")
                    time.sleep(random.uniform(0.5, 1.0))

                    # Clic en 'Siguiente' (después de ingresar cédula)
                    next_button_cedula = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next")))
                    try:
                        driver.execute_script("arguments[0].click();", next_button_cedula)
                        print(f"Hilo {thread_id}: Clic en 'Siguiente' (cédula).")
                    except ElementClickInterceptedException:
                        print(f"Hilo {thread_id}: Clic interceptado. JS para 'Siguiente'.")
                        driver.execute_script("arguments[0].click();", next_button_cedula)
                    time.sleep(random.uniform(0.5, 1.0))

                    if not wait_for_document_complete(driver, 10):
                        raise TimeoutException("Página resultados no cargada.")

                    if check_for_permanence_error(driver):
                        print(f"Hilo {thread_id}: Error de permanencia en resultados para {cedula_actual}. Reintentando...")
                        raise WebDriverException("Error de tiempo de permanencia.")

                    # Extraer y Guardar Información
                    extracted_data = extract_page_data(driver, cedula_actual)
                    with csv_lock: 
                        with open(output_csv_filename, "a", encoding="utf-8", newline='') as temp_csv_file:
                            csv_writer_thread = csv.writer(temp_csv_file)
                            csv_writer_thread.writerow([
                                extracted_data["cedula"],
                                extracted_data["nombre"],
                                extracted_data["apellido"],
                                extracted_data["fecha_nacimiento"],
                                extracted_data["seccion_judicial"]
                            ])
                    print(f"Hilo {thread_id}: Datos guardados para cédula {cedula_actual}.")
                    
                    with processed_cedulas_lock:
                        # Añadir a la cola de eliminación para el hilo escritor
                        processed_for_deletion_queue.put(cedula_actual)
                        print(f"Hilo {thread_id}: Cédula {cedula_actual} añadida a la cola de eliminación.") 
                    
                    cedula_processed_successfully = True # Marcar como exitoso
                    break # Salir del bucle de reintentos para esta cédula

                except WebDriverException as e: # Captura errores específicos de WebDriver
                    print(f"Hilo {thread_id}: Error WebDriver en cédula {cedula_actual} (Intento {cedula_attempt + 1}): {type(e).__name__} - {e}.")
                    if driver:
                        try:
                            print(f"Hilo {thread_id}: Captura guardada.")
                        except Exception as screenshot_err:
                            print(f"Hilo {thread_id}: Error al guardar captura: {screenshot_err}")
                        try:
                            driver.quit()
                            print(f"Hilo {thread_id}: WebDriver cerrado por error en intento.")
                        except Exception as ex_quit:
                            print(f"Hilo {thread_id}: Error al cerrar WebDriver: {ex_quit}.")
                    
                    if user_data_dir:
                        time.sleep(0.5) 
                        try:
                            shutil.rmtree(user_data_dir)
                            print(f"Hilo {thread_id}: Dir temporal eliminado.")
                        except OSError as os_e:
                            print(f"Hilo {thread_id}: Error al eliminar dir temporal '{user_data_dir}': {os_e}.")
                        except Exception as generic_e:
                            print(f"Hilo {thread_id}: Error inesperado al eliminar dir temporal '{user_data_dir}': {generic_e}.")
                    
                    if cedula_attempt == MAX_RETRIES - 1:
                        print(f"Hilo {thread_id}: Cédula {cedula_actual} FALLÓ después de {MAX_RETRIES} intentos. NO se eliminará de {CEDULAS_FILENAME}.") # Clarificar
                        break # Salir del bucle de reintentos para esta cédula
                
                except Exception as e: # Captura cualquier otra excepción
                    print(f"Hilo {thread_id}: Error inesperado en cédula {cedula_actual} (Intento {cedula_attempt + 1}): {type(e).__name__}.")
                    if driver:
                        try:
                            driver.save_screenshot(f"error_screenshot_cedula_{cedula_actual}_hilo_{thread_id}_attempt_{cedula_attempt + 1}.png")
                            print(f"Hilo {thread_id}: Captura guardada.")
                        except Exception as screenshot_err:
                            print(f"Hilo {thread_id}: Error al guardar captura: {screenshot_err}")
                        try:
                            driver.quit()
                            print(f"Hilo {thread_id}: WebDriver cerrado por error en intento.")
                        except Exception as ex_quit:
                            print(f"Hilo {thread_id}: Error al cerrar WebDriver: {ex_quit}.")
                    
                    if user_data_dir:
                        time.sleep(0.5) 
                        try:
                            shutil.rmtree(user_data_dir)
                            print(f"Hilo {thread_id}: Dir temporal eliminado.")
                        except OSError as os_e:
                            print(f"Hilo {thread_id}: Error al eliminar dir temporal '{user_data_dir}': {os_e}.")
                        except Exception as generic_e:
                            print(f"Hilo {thread_id}: Error inesperado al eliminar dir temporal '{user_data_dir}': {generic_e}.")
                    
                    if cedula_attempt == MAX_RETRIES - 1:
                        print(f"Hilo {thread_id}: Cédula {cedula_actual} FALLÓ después de {MAX_RETRIES} intentos. NO se eliminará de {CEDULAS_FILENAME}.") # Clarificar
                        break # Salir del bucle de reintentos para esta cédula

            # Pequeña pausa antes de obtener la siguiente cédula de la cola
            time.sleep(random.uniform(1.0, 2.0)) 

        except queue.Empty:
            print(f"Hilo {thread_id}: Cola vacía. Terminando hilo.")
            break 
        except Exception as e:
            # Esta captura es para errores que ocurren *antes* de que comience el bucle de reintentos (ej. queue.Empty)
            # o si ocurre una excepción inesperada fuera del mecanismo de reintentos.
            print(f"Hilo {thread_id}: Error crítico para cédula {cedula_actual}: {type(e).__name__} - {e}.")
            # Asegurar la limpieza si ocurre un error fuera del bucle de reintentos interno
            if driver:
                try:
                    driver.quit()
                    print(f"Hilo {thread_id}: WebDriver cerrado por error crítico.")
                except Exception as ex_quit:
                    print(f"Hilo {thread_id}: Error al cerrar WebDriver: {ex_quit}.")
            if user_data_dir:
                time.sleep(0.5) 
                try:
                    shutil.rmtree(user_data_dir)
                    print(f"Hilo {thread_id}: Dir temporal eliminado.")
                except OSError as os_e:
                    print(f"Hilo {thread_id}: Error al eliminar dir temporal '{user_data_dir}': {os_e}.")
                except Exception as generic_e:
                    print(f"Hilo {thread_id}: Error inesperado al eliminar dir temporal '{user_data_dir}': {generic_e}.")
            time.sleep(5) # Pausa después de un error crítico

    print(f"Hilo {thread_id}: Proceso completado.")


def main_automation_multi_thread():
    """Función principal para orquestar la automatización multi-hilo."""
    qa_pairs = load_qa_pairs(QA_FILENAME)
    all_cedulas = load_cedulas(CEDULAS_FILENAME)

    if not all_cedulas:
        print(f"No hay cédulas para procesar.")
        return
    
    cedula_queue = queue.Queue()
    random.shuffle(all_cedulas) 
    for cedula in all_cedulas:
        cedula_queue.put(cedula)

    # processed_cedulas_set y processed_cedulas_lock ahora se usan para la comunicación entre hilos de trabajo y el escritor
    # y para el reporte final de cédulas no procesadas.
    processed_cedulas_set = set() 
    processed_cedulas_lock = threading.Lock() 

    csv_lock = threading.Lock() 

    if not os.path.exists(OUTPUT_CSV_FILENAME) or os.stat(OUTPUT_CSV_FILENAME).st_size == 0:
        with open(OUTPUT_CSV_FILENAME, "w", encoding="utf-8", newline='') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(["cedula", "nombre", "apellido", "fecha_nacimiento", "seccion_judicial"])
        print(f"CSV '{OUTPUT_CSV_FILENAME}' inicializado.")
    else:
        print(f"CSV '{OUTPUT_CSV_FILENAME}' ya existe. Añadiendo datos.")

    MAX_CONCURRENT_THREADS = 7
    
    # Iniciar el hilo escritor antes que los hilos de trabajo
    writer_thread = threading.Thread(target=file_writer_thread_function)
    writer_thread.start()
    print("Hilo Escritor iniciado en segundo plano.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_THREADS) as executor:
        futures = []
        for i in range(MAX_CONCURRENT_THREADS):
            futures.append(executor.submit(worker_thread_function, i + 1, qa_pairs, OUTPUT_CSV_FILENAME, csv_lock, cedula_queue, processed_cedulas_set, processed_cedulas_lock))
            time.sleep(random.uniform(0.5, 1.5)) # Pausa entre lanzamiento de hilos

        for future in concurrent.futures.as_completed(futures):
            try:
                future.result() 
            except Exception as exc:
                print(f'Un hilo de trabajo generó una excepción: {exc}')

    print("\nTodos los hilos de trabajo han terminado. Señalando al hilo escritor para que finalice.")
    stop_writer_event.set() # Señalar al hilo escritor para que se detenga
    writer_thread.join() # Esperar a que el hilo escritor termine

    print("Proceso multi-hilo completado.")

    # La lógica de reescritura final del archivo se ha movido al hilo escritor.
    # Esta sección solo se encargará de reportar las cédulas que NO fueron procesadas exitosamente
    # por ningún hilo (incluyendo los reintentos) y por lo tanto no fueron añadidas a la cola de eliminación.
    
    # Para el reporte final, leemos el archivo *actual* de cédulas para ver cuáles quedan.
    final_remaining_cedulas = []
    try:
        with open(CEDULAS_FILENAME, "r", encoding="utf-8") as f_read:
            for line in f_read:
                final_remaining_cedula = line.strip()
                if final_remaining_cedula: # Solo añadir si no está vacío
                    final_remaining_cedulas.append(final_remaining_cedula)
        print(f"Cédulas restantes en '{CEDULAS_FILENAME}' después de la ejecución: {len(final_remaining_cedulas)}")
        if final_remaining_cedulas:
            print("Cédulas que NO fueron procesadas exitosamente y permanecen en el archivo:")
            for cedula in final_remaining_cedulas:
                print(f"- {cedula}")
        else:
            print("Todas las cédulas fueron procesadas exitosamente y eliminadas del archivo.")

    except FileNotFoundError:
        print(f"El archivo '{CEDULAS_FILENAME}' no se encontró al intentar verificar las cédulas restantes.")
    except Exception as e:
        print(f"Error al verificar las cédulas restantes en '{CEDULAS_FILENAME}': {e}")


if __name__ == "__main__":
    main_automation_multi_thread()
