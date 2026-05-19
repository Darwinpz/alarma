import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"mp3", "wav"}

HOST = "127.0.0.1"
PORT = 5000
SECRET_KEY = "school-bell-secret-2024"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
