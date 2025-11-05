# -*- блядь обнова сучка ты ебаная -*-
import os
import base64
from Crypto.Cipher import AES
from Crypto.Hash import SHA256


class EncryptionManager:
	def __init__(self, password=None):
		if password:
			key = SHA256.new(password.encode('utf-8')).digest()
		else:
			key = os.urandom(32)
		self.key = key

	def get_key_b64(self) -> str:
		return base64.b64encode(self.key).decode('utf-8')

	def set_key_b64(self, key_b64: str) -> None:
		self.key = base64.b64decode(key_b64.encode('utf-8'))

	def encrypt(self, plaintext: str) -> str:
		data = plaintext.encode('utf-8')
		nonce = os.urandom(12)
		cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
		ciphertext, tag = cipher.encrypt_and_digest(data)
		packed = nonce + tag + ciphertext
		return base64.b64encode(packed).decode('utf-8')

	def decrypt(self, encrypted_data: str) -> str:
		packed = base64.b64decode(encrypted_data.encode('utf-8'))
		nonce = packed[:12]
		tag = packed[12:28]
		ciphertext = packed[28:]
		cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
		data = cipher.decrypt_and_verify(ciphertext, tag)
		return data.decode('utf-8')

	def encrypt_bytes(self, raw: bytes) -> str:
		nonce = os.urandom(12)
		cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
		ciphertext, tag = cipher.encrypt_and_digest(raw)
		packed = nonce + tag + ciphertext
		return base64.b64encode(packed).decode('utf-8')

	def decrypt_bytes(self, encrypted_data: str) -> bytes:
		packed = base64.b64decode(encrypted_data.encode('utf-8'))
		nonce = packed[:12]
		tag = packed[12:28]
		ciphertext = packed[28:]
		cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
		return cipher.decrypt_and_verify(ciphertext, tag)

	@staticmethod
	def generate_shared_key(password: str) -> bytes:
		return SHA256.new(password.encode('utf-8')).digest()

