from flask import Flask, render_template, request, send_from_directory, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import threading
from main import (setup_chrome_driver, login, process_lessons, get_course_name,
                   sanitize_filename, handle_alert)
import zipfile
import io
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
import time


app = Flask(__name__)
# Configurações do Flask-SocketIO
socketio = SocketIO(app)

# Diretório onde os arquivos baixados serão armazenados
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
# Variável global para controlar o estado do download
DOWNLOAD_COMPLETE = False

@app.route('/')
def index():
    return render_template('form.html')

@app.route('/download', methods=['POST'])
def download():
    # Obtém os dados do formulário
    username = request.form['username']
    password = request.form['password']
    url = request.form['url']

    # Cria um diretório de downloads
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Executa o script em uma thread separada
    def run_script():
        global DOWNLOAD_DIR, DOWNLOAD_COMPLETE
        # Limpa o diretório de downloads antes de iniciar um novo download
        driver = setup_chrome_driver(DOWNLOAD_DIR, headless=False)
        try:
            driver.get(url)
            login(driver, username, password)

        #TODO: Melhorar a espera para evitar o uso de sleep
            # Aguarda até que a página de lições esteja carregada
            try:
                # Aguarda a presença do alerta antes de tentar fechá-lo
                WebDriverWait(driver, 20).until(EC.alert_is_present())
                handle_alert(driver)
                
                # Aguarda até que a página de lições esteja carregada
                WebDriverWait(driver, 30).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "LessonList-item"))
                )
                logging.info("Página de lições carregada com sucesso.")
            except Exception as e:
                logging.error(f"Erro ao carregar a página de lições: {e}")
                socketio.emit('download_error', {'message': 'Erro ao carregar a página de lições.'}, namespace='/')
                return
            # Fecha alertas, se presentes
            handle_alert(driver)
            process_lessons(driver, DOWNLOAD_DIR)
            course_name = get_course_name(driver)
            course_name_dir = os.path.join(os.getcwd(), sanitize_filename(course_name))
            os.rename(DOWNLOAD_DIR, course_name_dir)
            DOWNLOAD_DIR = course_name_dir
            DOWNLOAD_COMPLETE = True
            # Notifica o cliente quando o download é concluído
            socketio.emit('download_complete', {'message': 'Download concluído com sucesso!'}, namespace='/')
        except Exception as e:
            print(f"Erro: {e}")
            socketio.emit('download_error', {'message': 'Ocorreu um erro durante o download.'}, namespace='/')
        finally:
            driver.quit()

    threading.Thread(target=run_script).start()
    return jsonify({"message": "O download foi iniciado. Você será notificado quando terminar."})

@app.route('/files', methods=['GET'])
def list_files():
    """
    Renderiza a página com os arquivos disponíveis para download.
    """
    if not os.path.exists(DOWNLOAD_DIR):
        return render_template('files.html', files=[])

    files = []
    for root, dirs, filenames in os.walk(DOWNLOAD_DIR):
        for filename in filenames:
            # Adiciona o caminho relativo do arquivo
            files.append(os.path.relpath(os.path.join(root, filename), DOWNLOAD_DIR))
    return render_template('files.html', files=files)

@app.route('/files/<path:filename>', methods=['GET'])
def serve_file(filename):
    """
    Permite o download de um arquivo específico.
    """
    try:
        return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "Arquivo não encontrado."}), 404

@app.route('/files/download_all', methods=['GET'])
def download_all_files():
    """
    Compacta todos os arquivos disponíveis em um único arquivo .zip e o disponibiliza para download.
    """
    if not os.path.exists(DOWNLOAD_DIR):
        return jsonify({"error": "Nenhum arquivo disponível para download."}), 404

    # Cria um arquivo .zip em memória
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, filenames in os.walk(DOWNLOAD_DIR):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, DOWNLOAD_DIR)  # Caminho relativo no .zip
                zip_file.write(file_path, arcname)
    zip_buffer.seek(0)

    # Retorna o arquivo .zip para download
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=os.path.basename(DOWNLOAD_DIR) + '.zip'
    )

if __name__ == '__main__':
    app.run(debug=True)
