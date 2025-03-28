from flask import Flask, render_template, request, redirect, url_for
import os
import threading
from main import setup_chrome_driver, login, process_lessons, get_course_name, sanitize_filename

app = Flask(__name__)

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
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    # Executa o script em uma thread separada
    def run_script():
        driver = setup_chrome_driver(download_dir, headless=False)
        try:
            driver.get(url)
            login(driver, username, password)
            lessons_data = process_lessons(driver, download_dir)
            course_name = get_course_name(driver)
            course_name_dir = os.path.join(os.getcwd(), sanitize_filename(course_name))
            os.rename(download_dir, course_name_dir)
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            driver.quit()

    threading.Thread(target=run_script).start()
    return "O download foi iniciado. Verifique os logs para mais informações."

if __name__ == '__main__':
    app.run(debug=True)
