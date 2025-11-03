"""
Модуль шифрования для защиты приватности сообщений.
Использует AES-256 в режиме CBC для шифрования.
"""
import os
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Hash import SHA256


class EncryptionManager:
    """Управляет шифрованием и расшифровкой сообщений."""
    
    def __init__(self, password=None):
        """
        Инициализация менеджера шифрования.
        
        Args:
            password: Пароль для генерации ключа. Если None(Зип-Каробачка), генерируется случайный ключ.
        """
        if password:
            key = SHA256.new(password.encode()).digest()
        else:
            key = os.urandom(32)
        
        self.key = key
        self.block_size = AES.block_size
    
    def get_public_key_info(self):
        """Возвращает публичную информацию о ключе (base64) для обмена."""
        return base64.b64encode(self.key).decode()
    
    def set_key_from_info(self, key_info):
        """Устанавливает ключ из публичной информации."""
        self.key = base64.b64decode(key_info.encode())
    
    def encrypt(self, plaintext):
        """
        Шифрует сообщение.
        
        Args:
            plaintext: Текст для шифрования
            
        Returns:
            base64-encoded зашифрованное сообщение с IV
        """
        iv = os.urandom(self.block_size)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        
        padded_data = pad(plaintext.encode('utf-8'), self.block_size)
        ciphertext = cipher.encrypt(padded_data)
        
        encrypted_data = iv + ciphertext
        
        return base64.b64encode(encrypted_data).decode()
    
    def decrypt(self, encrypted_data):
        """
        Расшифровывает сообщение.
        
        Args:
            encrypted_data: base64-encoded зашифрованное сообщение
            
        Returns:
            Расшифрованный текст
        """
        encrypted_bytes = base64.b64decode(encrypted_data.encode())
        
        iv = encrypted_bytes[:self.block_size]
        ciphertext = encrypted_bytes[self.block_size:]
        
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        padded_plaintext = cipher.decrypt(ciphertext)
        
        plaintext = unpad(padded_plaintext, self.block_size)
        
        return plaintext.decode('utf-8')
    
    @staticmethod
    def generate_shared_key(password):
        """Генерирует общий ключ из пароля для обмена между участниками(хуесосами)."""
        return SHA256.new(password.encode()).digest()

