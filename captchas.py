import time
import random
import shutil 
import tempfile 
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, NoSuchElementException, ElementClickInterceptedException, WebDriverException

# Número máximo de reintentos para cada operación crítica
# Se establece en 1 para que no haya reintentos por paso individual
MAX_RETRIES = 1 

def wait_for_document_complete(driver, timeout=2): # Timeout reducido a 7 segundos
    """Espera hasta que el document.readyState del navegador sea 'complete'."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        print(f"Documento listo (readyState: complete) en {timeout} segundos.")
        return True
    except TimeoutException:
        print(f"Timeout: El documento no alcanzó 'readyState: complete' en {timeout} segundos.")
        return False

def extract_question_from_page(driver):
    """
    Extrae la pregunta de seguridad de la página actual, sin buscar en iframes.
    Relanza las excepciones (TimeoutException, NoSuchElementException, StaleElementReferenceException)
    si la pregunta no puede ser extraída.
    """
    try:
        # XPath más genérico para capturar la pregunta
        # Busca un label dentro de 'captcha-pregunta' o cualquier elemento con texto de pregunta común
        question_element = WebDriverWait(driver, 3).until( # Timeout reducido a 5 segundos
            EC.visibility_of_element_located((By.XPATH, "//*[contains(@class, 'captcha-pregunta')]//label | //label[contains(text(), '¿Cuál es') or contains(text(), '¿Cuántos') or contains(text(), '¿Qué número') or contains(text(), '¿Qué día')]"))
        )
        question_text = question_element.text.strip()
        print(f"Pregunta extraída del contenido principal: {question_text}")
        return question_text
    except (TimeoutException, NoSuchElementException, StaleElementReferenceException) as e:
        print(f"Error al extraer la pregunta: {e}")
        if isinstance(e, TimeoutException):
            print("Timeout: La pregunta de seguridad no apareció a tiempo.")
        elif isinstance(e, StaleElementReferenceException):
            print("Stale Element: El elemento de la pregunta se volvió obsoleto. La página pudo haberse recargado.")
        elif isinstance(e, NoSuchElementException):
            print("No Such Element: El elemento de la pregunta no fue encontrado en el DOM.")
        raise # Relanza la excepción para que el bloque principal la capture
    except Exception as e:
        print(f"Error inesperado al extraer la pregunta: {e}")
        raise # Relanza cualquier otra excepción inesperada

def check_for_permanence_error(driver):
    """
    Verifica si el error de "tiempo de permanencia" está presente en la página.
    """
    try:
        # Buscar el div con el mensaje de error de permanencia
        # Usamos WebDriverWait para esperar que el elemento sea visible, si existe
        error_element = WebDriverWait(driver, 3).until( # Timeout reducido a 3 segundos
            EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'El tiempo de permanencia en el paso actual no puede superar los dos minutos')]"))
        )
        if error_element: # Si se encontró y es visible
            print("¡Error de 'tiempo de permanencia' detectado en la página!")
            return True
    except TimeoutException: # Si el elemento no aparece en el tiempo dado
        return False
    except NoSuchElementException: # Si el elemento no está en el DOM
        return False
    except Exception as e:
        print(f"Error al verificar el error de permanencia: {e}")
        return False
    return False


def automate_process(num_repetitions=10):
    """
    Automatiza el proceso de navegación y extracción de la pregunta.
    """
    # URL de destino actualizada con el parámetro jfwid
    url = "https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid=PyjvkRHW245PPMAlAM6HJ1CNwqGB-yY7iMv8-6QH:0"
    
    # Archivo para guardar las preguntas
    output_filename = "preguntas_seguridad.txt"

    # Abrir el archivo en modo de añadir ("a") para que cada nueva pregunta se agregue al final
    with open(output_filename, "a", encoding="utf-8") as f:
        for i in range(num_repetitions):
            driver = None # Inicializar driver a None para cada iteración
            user_data_dir = None # Inicializar user_data_dir a None
            print(f"\n--- Repetición {i+1}/{num_repetitions} ---")
            try:
                # Crear un directorio temporal para el perfil de usuario de Chrome
                user_data_dir = tempfile.mkdtemp()
                print(f"Directorio temporal creado: {user_data_dir}")

                # Configurar opciones de Chrome para modo no-headless (visible) y stealth
                chrome_options = Options()
                # chrome_options.add_argument("--headless")  # Descomentado para que no sea headless
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu") # Para algunos sistemas, es necesario
                chrome_options.add_argument("--window-size=1920,1080") # Asegura un tamaño de ventana adecuado
                chrome_options.add_argument(f"--user-data-dir={user_data_dir}") # Usar el directorio temporal
                
                # Opciones adicionales para intentar ser menos detectable
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-infobars")
                chrome_options.add_argument("--disable-browser-side-navigation")
                chrome_options.add_argument("--disable-features=VizDisplayCompositor")
                chrome_options.add_argument("--disable-popup-blocking")
                
                # Añadir un User-Agent para simular un navegador real (cambiado ligeramente)
                user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
                chrome_options.add_argument(f"user-agent={user_agent}")

                # Inicializar el servicio de Chrome driver y el driver en cada repetición
                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                print("WebDriver inicializado para esta repetición.")

                # 1. Navegar a la URL
                driver.get(url)
                print(f"Navegando a: {url}")
                
                # Espera aleatoria inicial para que la página cargue completamente
                time.sleep(random.uniform(0.3, 0.5)) # Rango reducido

                # Espera hasta que el documento esté completamente cargado
                if not wait_for_document_complete(driver, 0): # Timeout reducido
                    print("La página inicial no cargó completamente a tiempo. Saltando a la siguiente repetición.")
                    raise TimeoutException("Página inicial no cargada.") # Relanzar para manejar en el except principal
                
                # Verificar si el error de permanencia ya está presente
                if check_for_permanence_error(driver):
                    print("Error de 'tiempo de permanencia' detectado al inicio de la repetición. Reiniciando.")
                    raise WebDriverException("Error de tiempo de permanencia al inicio.")

                # --- Paso: Clic en 'Acepto los términos' ---
                try:
                    accept_terms_radio = WebDriverWait(driver, 3).until( # Timeout reducido
                        EC.element_to_be_clickable((By.ID, "formTitulo:consentimientoView:b_nie:0"))
                    )
                    if not accept_terms_radio.is_selected():
                        driver.execute_script("arguments[0].click();", accept_terms_radio)
                        print("Clic en 'Acepto los términos' (usando JavaScript).")
                except Exception as e:
                    print(f"Error al hacer clic en 'Acepto los términos': {e}. Saltando a la siguiente repetición.")
                    raise # Relanzar para manejar en el except principal

                # Espera aleatoria después de hacer clic en los términos
                time.sleep(random.uniform(0.2, 0.8)) # Rango reducido

                # --- Paso: Clic en 'Siguiente' ---
                try:
                    next_button = WebDriverWait(driver, 3).until( # Timeout reducido
                        EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next"))
                    )
                    driver.execute_script("arguments[0].click();", next_button)
                    print("Clic en 'Siguiente' (usando JavaScript).")
                except Exception as e:
                    print(f"Error al hacer clic en 'Siguiente': {e}. Saltando a la siguiente repetición.")
                    raise # Relanzar para manejar en el except principal

                # Espera explícita para la página de la pregunta (document.readyState completo)
                if not wait_for_document_complete(driver, 0.5): # Timeout reducido
                    print("La página de la pregunta de seguridad no cargó completamente a tiempo. Saltando a la siguiente repetición.")
                    raise TimeoutException("Página de pregunta no cargada.") # Relanzar para manejar en el except principal
                
                # Verificar si el error de permanencia aparece después de hacer clic en Siguiente
                if check_for_permanence_error(driver):
                    print("Error de 'tiempo de permanencia' detectado después de hacer clic en Siguiente. Reiniciando.")
                    raise WebDriverException("Error de tiempo de permanencia después de Siguiente.")

                # 4. Copiar en un txt lo que hay abajo de "Responda la pregunta para continuar:"
                question = extract_question_from_page(driver)
                # Modificación para el formato de salida solicitado: pregunta,x
                f.write(f"{question},{i+1}\n")
                f.flush() # Fuerza la escritura inmediata al disco
                print(f"Pregunta guardada en '{output_filename}'.")

            except Exception as e:
                # Este bloque captura cualquier excepción no manejada en los pasos anteriores,
                # incluyendo las relanzadas por extract_question_from_page
                print(f"Ocurrió un error en la repetición {i+1}: {e}. Saltando a la siguiente repetición.")
                # Opcional: tomar una captura de pantalla para depurar
                if driver: # Asegurarse de que el driver existe antes de tomar captura
                    driver.save_screenshot(f"error_screenshot_repetition_{i+1}.png")
                    print(f"Captura de pantalla guardada como 'error_screenshot_repetition_{i+1}.png'")
                
                # Cerrar el WebDriver actual si está abierto
                if driver:
                    driver.quit()
                    print("WebDriver cerrado debido a un error.")
                
                time.sleep(10) # Espera 10 segundos después del error antes de la siguiente repetición
                
            finally:
                # Asegurarse de que el WebDriver se cierre al final de cada repetición,
                # incluso si no hubo un error en el bloque try-except.
                if driver and driver.session_id: # Verificar si el driver existe y la sesión está activa
                    driver.quit()
                    print("WebDriver cerrado al finalizar la repetición.")
                
                # Eliminar el directorio temporal del perfil de usuario
                if user_data_dir:
                    shutil.rmtree(user_data_dir)
                    print("Directorio temporal eliminado.")
                
            # Pequeña pausa aleatoria entre repeticiones para evitar sobrecargar el servidor
            time.sleep(random.uniform(0.3, 0.5)) # Rango reducido

    print(f"\nProceso completado. Las preguntas se han guardado en '{output_filename}'.")

if __name__ == "__main__":
    automate_process(num_repetitions=100)
