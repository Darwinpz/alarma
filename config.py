import os
import sys

# Cuando corre como .exe (PyInstaller), sys.executable apunta al .exe real.
# Cuando corre como script Python normal, usa la carpeta del archivo.
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"mp3", "wav"}

HOST = "127.0.0.1"
PORT = 5000
SECRET_KEY = "school-bell-secret-2024"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
