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
    """
    Configura o driver do Chrome com as opções necessárias para o download de arquivos PDF.
    
    Args:
        download_dir (str): Diretório onde os arquivos serão baixados.
        headless (bool): Se True, o navegador será executado em modo headless (sem interface gráfica).
    
    Returns:
        WebDriver: Instância do WebDriver configurada.
    """
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
    """
    Remove caracteres inválidos de um nome de arquivo para o Windows.
    
    Args:
        filename (str): Nome do arquivo a ser sanitizado.
    
    Returns:
        str: Nome do arquivo sanitizado.
    """
    return re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', filename)

def truncate_filename(filename, max_length=150):
    """
    Trunca o nome do arquivo se ele exceder um comprimento máximo.
    
    Args:
        filename (str): Nome do arquivo a ser truncado.
        max_length (int): Comprimento máximo permitido para o nome do arquivo.
    
    Returns:
        str: Nome do arquivo truncado.
    """
    if len(filename) > max_length:
        logging.warning(f"Nome da aula muito longo, truncando para {max_length} caracteres")
        filename = filename[:max_length]
    return filename

def get_lesson_name(lesson_element):
    """
    Obtém o nome da aula a partir dos elementos HTML.
    
    Args:
        lesson_element (WebElement): Elemento da aula contendo os detalhes.
    
    Returns:
        str: Nome da aula sanitizado e truncado.
    """
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
    """
    Renomeia o arquivo PDF mais recente baixado no diretório de downloads.
    
    Args:
        download_dir (str): Diretório onde os arquivos são baixados.
        new_name (str): Novo nome para o arquivo baixado.
    """
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

def click_ignore_survey(driver):
    """
    Clica no botão "Ignorar pesquisa" se o modal de pesquisa aparecer.
    
    Args:
        driver (WebDriver): Instância do WebDriver.
    
    Returns:
        bool: True se o botão foi clicado com sucesso, False caso contrário.
    """
    try:
        # Espera até que o modal esteja presente
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "ReactModalPortal"))
        )
        # Espera até que o botão "Ignorar pesquisa" esteja presente e clicável
        ignore_button = WebDriverWait(modal, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[text()='Ignorar pesquisa']"))
        )
        ignore_button.click()
        logging.info("Botão 'Ignorar pesquisa' clicado.")
        logging.info("Aguardando 2 segundos para fechar o modal...")
        time.sleep(2)
        try:
            # Espera até que o botão de fechar o modal esteja presente e clicável
            close_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Fechar Modal']"))
            )
            close_button.click()
            logging.info("Botão de fechar modal clicado.")
            return True
        except Exception as e:
            logging.error(f"Erro ao clicar no ícone de fechar modal: {e}")
            return False
    except Exception as e:
        logging.error(f"Erro ao clicar no botão 'Ignorar pesquisa': {e}")
        return False

def process_lesson_buttons(driver, lesson_element, download_dir, wait_time=1):
    """
    Processa os botões de download de uma aula e renomeia os arquivos baixados.
    
    Args:
        driver (WebDriver): Instância do WebDriver.
        lesson_element (WebElement): Elemento da aula contendo os botões de download.
        download_dir (str): Diretório onde os arquivos são baixados.
        wait_time (int): Tempo de espera entre downloads.
    
    Returns:
        list: Lista de URLs dos arquivos baixados.
    """
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
    """
    Encontra os botões de download de PDF em um elemento de aula.
    
    Args:
        lesson_element (WebElement): Elemento da aula contendo os botões de download.
    
    Returns:
        list: Lista de elementos de botão de download.
    """
    return lesson_element.find_elements(By.CSS_SELECTOR,
        '.LessonButton[href^="https://api.estrategiaconcursos.com.br/api/aluno/pdf/download/"]'
    )

def initiate_download(driver, button, url):
    """
    Inicia o download de um arquivo PDF clicando no botão correspondente.
    
    Args:
        driver (WebDriver): Instância do WebDriver.
        button (WebElement): Elemento do botão de download.
        url (str): URL do arquivo a ser baixado.
    """
    try:
        driver.execute_script("arguments[0].click();", button)
        logging.info(f"Primeira tentativa de download para o URL: {url}")
        if click_ignore_survey(driver):
            driver.execute_script("arguments[0].click();", button)
            logging.info(f"Segunda tentativa de download para o URL: {url}")
    except Exception as e:
        logging.error(f"Erro ao iniciar o download para o URL: {url} - {e}")
    else:
        logging.info(f"Download iniciado para o URL: {url}")

def wait_for_download(download_dir, old_num_files=0, timeout=60):
    """
    Aguarda até que o download de um arquivo seja concluído.
    
    Args:
        download_dir (str): Diretório onde os arquivos são baixados.
        old_num_files (int): Número de arquivos no diretório antes do download.
        timeout (int): Tempo máximo de espera pelo download (em segundos).
    """
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
    """
    Abre uma aula clicando no cabeçalho correspondente.
    
    Args:
        driver (WebDriver): Instância do WebDriver.
        lesson_element (WebElement): Elemento da aula a ser aberta.
    """
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
    """
    Processa todas as aulas na página, baixando e renomeando os arquivos PDF.
    
    Args:
        driver (WebDriver): Instância do WebDriver.
        download_dir (str): Diretório onde os arquivos são baixados.
    
    Returns:
        list: Lista de dicionários contendo os nomes das aulas e os links dos arquivos baixados.
    """
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