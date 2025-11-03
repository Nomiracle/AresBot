import os
from cryptography.fernet import Fernet
from config import ENCRYPTION_KEY_FILE

def get_or_create_encryption_key():
    if os.path.exists(ENCRYPTION_KEY_FILE):
        with open(ENCRYPTION_KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(ENCRYPTION_KEY_FILE, 'wb') as f:
            f.write(key)
        return key

ENCRYPTION_KEY = get_or_create_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_data(data):
    if data is None:
        return None
    return cipher_suite.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data):
    if encrypted_data is None:
        return None
    try:
        return cipher_suite.decrypt(encrypted_data.encode()).decode()
    except Exception as e:
        # 解密失败时记录错误并返回空字符串（避免返回损坏的数据）
        print(f"[DECRYPT ERROR] 解密失败: {str(e)[:100]}, 数据前20字符: {encrypted_data[:20] if len(encrypted_data) > 20 else encrypted_data}")
        return ""  # 返回空字符串而不是None，避免前端显示undefined
