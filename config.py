import os

DB_FILE = 'aresbot.db'
ENCRYPTION_KEY_FILE = 'encryption.key'
PORT = 50001

def get_flask_secret_key():
    return os.urandom(24)
