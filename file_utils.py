import os, secrets
from werkzeug.utils import secure_filename
from config import Config

ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'txt', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED

def save_upload(file_storage, dest_folder):
    raw = secure_filename(file_storage.filename)
    token = secrets.token_hex(8)
    fname = f"{token}_{raw}"
    path = os.path.join(dest_folder, fname)
    file_storage.save(path)
    return fname, raw
