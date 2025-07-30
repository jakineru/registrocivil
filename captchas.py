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

MAX_RETRIES = 1 

def wait_for_document_complete(driver, timeout=2): 
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

        question_element = WebDriverWait(driver, 3).until( 
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
        raise 
    except Exception as e:
        print(f"Error inesperado al extraer la pregunta: {e}")
        raise 

def check_for_permanence_error(driver):
    """
    Verifica si el error de "tiempo de permanencia" está presente en la página.
    """
    try:

        error_element = WebDriverWait(driver, 3).until( 
            EC.visibility_of_element_located((By.XPATH, "//div[contains(text(), 'El tiempo de permanencia en el paso actual no puede superar los dos minutos')]"))
        )
        if error_element: 
            print("¡Error de 'tiempo de permanencia' detectado en la página!")
            return True
    except TimeoutException: 
        return False
    except NoSuchElementException: 
        return False
    except Exception as e:
        print(f"Error al verificar el error de permanencia: {e}")
        return False
    return False

def automate_process(num_repetitions=10):
    """
    Automatiza el proceso de navegación y extracción de la pregunta.
    """

    url = "https://dgrec.gub.uy/partidasdigitales/publico/solicitudPartidaNacimiento.xhtml?jfwid=PyjvkRHW245PPMAlAM6HJ1CNwqGB-yY7iMv8-6QH:0"

    output_filename = "preguntas_seguridad.txt"

    with open(output_filename, "a", encoding="utf-8") as f:
        for i in range(num_repetitions):
            driver = None 
            user_data_dir = None 
            print(f"\n--- Repetición {i+1}/{num_repetitions} ---")
            try:

                user_data_dir = tempfile.mkdtemp()
                print(f"Directorio temporal creado: {user_data_dir}")

                chrome_options = Options()

                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu") 
                chrome_options.add_argument("--window-size=1920,1080") 
                chrome_options.add_argument(f"--user-data-dir={user_data_dir}") 

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

                service = Service(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=chrome_options)
                print("WebDriver inicializado para esta repetición.")

                driver.get(url)
                print(f"Navegando a: {url}")

                time.sleep(random.uniform(0.3, 0.5)) 

                if not wait_for_document_complete(driver, 0): 
                    print("La página inicial no cargó completamente a tiempo. Saltando a la siguiente repetición.")
                    raise TimeoutException("Página inicial no cargada.") 

                if check_for_permanence_error(driver):
                    print("Error de 'tiempo de permanencia' detectado al inicio de la repetición. Reiniciando.")
                    raise WebDriverException("Error de tiempo de permanencia al inicio.")

                try:
                    accept_terms_radio = WebDriverWait(driver, 3).until( 
                        EC.element_to_be_clickable((By.ID, "formTitulo:consentimientoView:b_nie:0"))
                    )
                    if not accept_terms_radio.is_selected():
                        driver.execute_script("arguments[0].click();", accept_terms_radio)
                        print("Clic en 'Acepto los términos' (usando JavaScript).")
                except Exception as e:
                    print(f"Error al hacer clic en 'Acepto los términos': {e}. Saltando a la siguiente repetición.")
                    raise 

                time.sleep(random.uniform(0.2, 0.8)) 

                try:
                    next_button = WebDriverWait(driver, 3).until( 
                        EC.element_to_be_clickable((By.ID, "formTitulo:wizMatricula_next"))
                    )
                    driver.execute_script("arguments[0].click();", next_button)
                    print("Clic en 'Siguiente' (usando JavaScript).")
                except Exception as e:
                    print(f"Error al hacer clic en 'Siguiente': {e}. Saltando a la siguiente repetición.")
                    raise 

                if not wait_for_document_complete(driver, 0.5): 
                    print("La página de la pregunta de seguridad no cargó completamente a tiempo. Saltando a la siguiente repetición.")
                    raise TimeoutException("Página de pregunta no cargada.") 

                if check_for_permanence_error(driver):
                    print("Error de 'tiempo de permanencia' detectado después de hacer clic en Siguiente. Reiniciando.")
                    raise WebDriverException("Error de tiempo de permanencia después de Siguiente.")

                question = extract_question_from_page(driver)

                f.write(f"{question},{i+1}\n")
                f.flush() 
                print(f"Pregunta guardada en '{output_filename}'.")

            except Exception as e:

                print(f"Ocurrió un error en la repetición {i+1}: {e}. Saltando a la siguiente repetición.")

                if driver: 
                    driver.save_screenshot(f"error_screenshot_repetition_{i+1}.png")
                    print(f"Captura de pantalla guardada como 'error_screenshot_repetition_{i+1}.png'")

                if driver:
                    driver.quit()
                    print("WebDriver cerrado debido a un error.")

                time.sleep(10) 

            finally:

                if driver and driver.session_id: 
                    driver.quit()
                    print("WebDriver cerrado al finalizar la repetición.")

                if user_data_dir:
                    shutil.rmtree(user_data_dir)
                    print("Directorio temporal eliminado.")

            time.sleep(random.uniform(0.3, 0.5)) 

    print(f"\nProceso completado. Las preguntas se han guardado en '{output_filename}'.")

if __name__ == "__main__":
    automate_process(num_repetitions=100)