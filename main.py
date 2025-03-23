import os
import time
import re
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_chrome_driver(download_dir, headless=False):
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    if headless:
        chrome_options.add_argument("--headless")  # Adiciona a opção para rodar em modo headless
    chrome_options.add_argument("--disable-gpu")  # Necessário para algumas versões do Chrome
    chrome_options.add_argument("--window-size=1920x1080")  # Define o tamanho da janela
    return webdriver.Chrome(options=chrome_options)

def sanitize_filename(filename):
    # Remove caracteres inválidos para o Windows
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', filename)

def truncate_filename(filename, max_length=150):
    # Limita o nome do arquivo ao máximo permitido (150 caracteres)
    if len(filename) > max_length:
        logging.warning(f"Nome da aula muito longo, truncando para {max_length} caracteres")
        filename = filename[:max_length]
    return filename

def get_lesson_name(lesson_element):
    try:
        h2_text = lesson_element.find_element(By.TAG_NAME, "h2").text
        p_text = lesson_element.find_element(By.TAG_NAME, "p").text
        lesson_name = f"{h2_text} - {p_text}".replace("/", "-").replace("\\", "-")
        
        # Limpa e trunca o nome do arquivo
        lesson_name = sanitize_filename(lesson_name)
        lesson_name = truncate_filename(lesson_name)
        logging.info(f"Nome completo da aula: {lesson_name}")  # Imprime o nome completo da aula
        return lesson_name
    except Exception as e:
        logging.error(f"Erro ao obter o nome da aula: {e}")
        return "Aula_Sem_Nome"

def rename_downloaded_file(download_dir, new_name):
    files = os.listdir(download_dir)
    pdf_files = [f for f in files if f.endswith(".pdf")]
    if not pdf_files:
        logging.warning("Nenhum arquivo PDF novo encontrado para renomear.")
        return

    # Pega o arquivo PDF mais antigo que ainda não foi renomeado
    newest_file = max(pdf_files, key=lambda f: os.path.getctime(os.path.join(download_dir, f)))
    new_name = sanitize_filename(new_name)  # Remove caracteres inválidos
    new_path = os.path.join(download_dir, f"{new_name}.pdf")

    try:
        # Renomeia o arquivo
        os.rename(os.path.join(download_dir, newest_file), new_path)
        logging.info(f"Arquivo renomeado para: {new_path}")
    except Exception as e:
        logging.error(f"Erro ao renomear o arquivo: {e}")
        try:
            os.remove(os.path.join(download_dir, newest_file))
            logging.info(f"Arquivo deletado: {newest_file}")
        except Exception as delete_error:
            logging.error(f"Erro ao deletar o arquivo: {delete_error}")

def process_lesson_buttons(driver, lesson_element, download_dir, wait_time=1):
    pdf_buttons = find_pdf_buttons(lesson_element)
    if not pdf_buttons:
        logging.info("Nenhum botão relevante encontrado na aula.")
        return []

    lesson_name = get_lesson_name(lesson_element)
    num_files = len(os.listdir(download_dir))
    links = []
    for button in pdf_buttons:
        url = button.get_attribute("href")
        if url:
            links.append(url)
            try:
                initiate_download(driver, button, url)
                wait_for_download(download_dir, num_files)
                time.sleep(wait_time)  # Aguarda para garantir que o arquivo foi salvo
                rename_downloaded_file(download_dir, lesson_name)
            except Exception as e:
                logging.error(f"Erro ao clicar no botão de download: {e}")
        else:
            logging.error("Erro: URL do botão não encontrado.")
    return links

def find_pdf_buttons(lesson_element):
    return lesson_element.find_elements(By.CSS_SELECTOR,
        '.LessonButton[href^="https://api.estrategiaconcursos.com.br/api/aluno/pdf/download/"]'
    )

def initiate_download(driver, button, url):
    driver.execute_script("arguments[0].click();", button)
    logging.info(f"Download iniciado para o URL: {url}")

def wait_for_download(download_dir, old_num_files=0, timeout=60):
    for _ in range(timeout):
        files = os.listdir(download_dir)
        logging.info(f"Arquivos na pasta de downloads: {files}")
        new_num_files = len(files)
        if files and (files[-1].endswith('.pdf') and new_num_files > old_num_files):
            logging.info("Download concluído!")
            return
        time.sleep(1)
    logging.warning(f"Aviso: O download do arquivo demorou mais do que o esperado.")

def open_lesson(driver, lesson_element):
    try:
        lesson_header = lesson_element.find_element(By.CLASS_NAME, "Collapse-header")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lesson_header)
        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(lesson_header)).click()
        except:
            driver.execute_script("arguments[0].click();", lesson_header)
        time.sleep(2)
    except Exception as e:
        logging.error(f"Erro ao tentar abrir a aula: {e}")

def process_lessons(driver, download_dir):
    lessons = driver.find_elements(By.CLASS_NAME, "LessonList-item")
    if not lessons:
        logging.info("Nenhuma aula encontrada na página.")
        return []

    lessons_list = []
    for lesson in lessons:
        open_lesson(driver, lesson)
        time.sleep(3)
        lesson_links = process_lesson_buttons(driver, lesson, download_dir)
        lessons_list.append({
            "lessonName": f"Aula {len(lessons_list) + 1}",
            "lessonLinks": lesson_links
        })
        time.sleep(1)
    logging.info("Processamento das aulas concluído!")
    return lessons_list

if __name__ == "__main__":
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    # Solicita o URL ao usuário
    url = input("Digite o URL do curso (exemplo: https://www.estrategiaconcursos.com.br/app/dashboard/cursos/220866/aulas): ")

    # Inicializa o navegador sem headless para login manual
    driver = setup_chrome_driver(download_dir, headless=False)
    driver.get(url)

    input("Pressione Enter após realizar o login manual na página...")

    try:
        lessons_data = process_lessons(driver, download_dir)
        logging.info(f"Dados coletados: {lessons_data}")
        logging.info(f"Arquivos baixados em: {download_dir}")
    finally:
        driver.quit()