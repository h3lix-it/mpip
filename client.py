import socket
import threading
import select
import sys
import json
from protocol import MessageProtocol
from encryption import EncryptionManager


class DecentralizedClient:
	"""Базовый клиент MPIP (ну типо можно взять и использовать, если хочешь сделать свой клиент, а можешь так юзать)."""
	
	def __init__(self, server_host, server_port, username, password=None):
		"""
		Инициализация клиента.
		
		Args:
			server_host: Адрес сервера
			server_port: Порт сервера
			username: Имя пользователя
			password: Пароль для шифрования (опционально)
		"""
		self.server_host = server_host
		self.server_port = server_port
		self.username = username
		self.socket = None
		self.connected = False
		self.encryption_manager = EncryptionManager(password) if True else None
		self.shared_password = password
		self.users = []
		self.encrypt_default = True
		self._adopted_key = False
		self._session_key_owner = (self.username if not password else 'password')
	
	def connect(self):
		"""Подключается к серверу (подключение к твоей мамаше)."""
		try:
			self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socket.connect((self.server_host, self.server_port))
			self.connected = True
			
			print(f"Подключено к серверу {self.server_host}:{self.server_port}")
			
			join_msg = MessageProtocol.create_join_message(self.username)
			self.socket.send(join_msg.encode('utf-8'))
			
			if not self.shared_password and self.encryption_manager:
				key_b64 = self.encryption_manager.get_key_b64()
				kx = MessageProtocol.create_message(MessageProtocol.MSG_TYPE_KEY_EXCHANGE, key_b64, username=self.username)
				self.socket.send(kx.encode('utf-8'))
			
			receive_thread = threading.Thread(target=self._receive_messages, daemon=True)
			receive_thread.start()
			
			import time
			time.sleep(0.1)
			
			return True
			
		except Exception as e:
			print(f"Ошибка при подключении: {e}")
			self.connected = False
			return False
	
	def _receive_messages(self):
		"""Принимает сообщения от сервера."""
		buffer = ""
		
		self.socket.settimeout(1.0)
		
		while self.connected:
			try:
				data = self.socket.recv(8192).decode('utf-8', errors='ignore')
				
				if not data:
					print("\nСоединение с сервером потеряно", flush=True)
					self.connected = False
					break
				
				buffer += data
				
				while True:
					if '\n' in buffer:
						line, buffer = buffer.split('\n', 1)
						line = line.strip()
						if line:
							try:
								if line.startswith("Users:"):
									users_text = line.replace("Users:", "").strip()
									if users_text:
										print(f"\n> Пользователи онлайн: {users_text}", flush=True)
									else:
										print("\n> В сети нет других пользователей", flush=True)
									continue
								if line.startswith("Online:"):
									users_text = line.replace("Online:", "").strip()
									if users_text:
										print(f"\n> Пользователи онлайн: {users_text}", flush=True)
									else:
										print("\n> В сети нет других пользователей", flush=True)
									continue
								self._handle_message(line)
							except Exception as e:
								print(f"\n[ОШИБКА] Ошибка при обработке сообщения: {e}", flush=True)
								import traceback
								traceback.print_exc()
						continue
					
					stripped_buffer = buffer.strip()
					if stripped_buffer.startswith('{') and stripped_buffer.endswith('}'):
						try:
							json.loads(stripped_buffer)
							try:
								self._handle_message(stripped_buffer)
								buffer = ''
							except Exception as e:
								print(f"\n[ОШИБКА] Ошибка при обработке сообщения: {e}", flush=True)
								import traceback
								traceback.print_exc()
						except json.JSONDecodeError:
							break
					else:
						break
						
			except socket.timeout:
				continue
			except ConnectionResetError:
				print("\nСоединение с сервером потеряно", flush=True)
				self.connected = False
				break
			except Exception as e:
				print(f"\nОшибка при получении сообщения: {e}", flush=True)
				self.connected = False
				break
	
	def _handle_message(self, message_data):
		"""Обрабатывает полученное сообщение."""
		try:
			message = MessageProtocol.parse_message(message_data)
			if not message:
				return
			
			msg_type = message.get('type')
			content = message.get('content', '')
			sender = message.get('username', 'Система')
			
			if msg_type == MessageProtocol.MSG_TYPE_KEY_EXCHANGE:
				if self.shared_password:
					return
				if sender == self.username:
					return
				try:
					owner = sender if sender < self.username else self.username
					if owner == sender:
						if self._session_key_owner != sender or not self._adopted_key:
							self.encryption_manager.set_key_b64(content)
							self._adopted_key = True
							self._session_key_owner = sender
							print("[Сеансовый ключ принят]", flush=True)
					else:
						key_b64 = self.encryption_manager.get_key_b64()
						kx = MessageProtocol.create_message(MessageProtocol.MSG_TYPE_KEY_EXCHANGE, key_b64, username=self.username)
						self.socket.send(kx.encode('utf-8'))
					return
				except Exception as e:
					print(f"[Ошибка обработки KEY_EXCHANGE]: {e}", flush=True)
					return
			
			if msg_type == MessageProtocol.MSG_TYPE_MESSAGE:
				if sender == self.username:
					return
				
				if message.get('encrypted', False):
					try:
						if self.encryption_manager:
							decrypted_content = self.encryption_manager.decrypt(content)
							print(f"\n[{sender}]: {decrypted_content}", flush=True)
						else:
							print(f"\n[{sender}]: [зашифрованное сообщение - нет ключа]", flush=True)
					except Exception as e:
						print(f"\n[{sender}]: [ошибка расшифровки: {e}]", flush=True)
				else:
					print(f"\n[{sender}]: {content}", flush=True)
			
			elif msg_type == MessageProtocol.MSG_TYPE_JOIN:
				print(f"\n> {content}", flush=True)
				if sender not in self.users:
					self.users.append(sender)
			
			elif msg_type == MessageProtocol.MSG_TYPE_LEAVE:
				print(f"\n> {content}", flush=True)
				if sender in self.users:
					self.users.remove(sender)
			
			elif msg_type == MessageProtocol.MSG_TYPE_USER_LIST:
				try:
					self.users = json.loads(content)
					if self.username in self.users:
						self.users.remove(self.username)
					if self.users:
						print(f"\n> Пользователи онлайн: {', '.join(self.users)}", flush=True)
				except:
					pass
			
			elif msg_type == MessageProtocol.MSG_TYPE_FILE:
				self._handle_file(message)
			
			elif msg_type == MessageProtocol.MSG_TYPE_PONG:
				pass
		
		except Exception as e:
			print(f"\n[ОШИБКА] Ошибка при обработке сообщения: {e}", flush=True)
			import traceback
			traceback.print_exc()
	
	def _handle_file(self, message):
		"""Обрабатывает полученный файл."""
		filename = message.get('filename', 'unknown_file')
		file_data_base64 = message.get('file_data', '')
		file_size = message.get('file_size', 0)
		sender = message.get('username', 'Система')
		encrypted = message.get('encrypted', False)
		
		if sender == self.username:
			return
		
		try:
			import base64
			import os
			
			if encrypted:
				if not self.encryption_manager:
					print(f"\n[{sender}]: [файл {filename} зашифрован - нет ключа]", flush=True)
					return
				try:
					file_data = self.encryption_manager.decrypt_bytes(file_data_base64)
				except Exception as decrypt_error:
					print(f"\n[{sender}]: [ошибка расшифровки файла {filename}: {decrypt_error}]", flush=True)
					print(f"  → Проверьте, что у вас синхронизирован ключ шифрования", flush=True)
					return
			else:
				try:
					file_data = base64.b64decode(file_data_base64)
				except Exception as decode_error:
					print(f"\n[{sender}]: [пошел нахуй: ошибка декодирования файла {filename}: {decode_error}]", flush=True)
					return
			
			if not file_data:
				print(f"\n[{sender}]: [пососи: файл {filename} пуст после расшифровки]", flush=True)
				return
			
			downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
			if not os.path.exists(downloads_dir):
				try:
					os.makedirs(downloads_dir, exist_ok=True)
				except Exception as mkdir_error:
					print(f"\n[{sender}]: [пососи: ошибка создания папки downloads: {mkdir_error}]", flush=True)
					downloads_dir = os.getcwd()
			
			import time
			safe_filename = os.path.basename(filename)
			timestamp = int(time.time())
			save_path = os.path.join(downloads_dir, f"{timestamp}_{safe_filename}")
			
			try:
				with open(save_path, 'wb') as f:
					f.write(file_data)
					f.flush()
					os.fsync(f.fileno())
			except Exception as write_error:
				print(f"\n[{sender}]: [ошибка записи файла {filename}: {write_error}]", flush=True)
				return
			
			if not os.path.exists(save_path):
				print(f"\n[{sender}]: [пососи: файл {filename} не был создан после записи]", flush=True)
				return
			
			actual_size = os.path.getsize(save_path)
			if actual_size == 0:
				print(f"\n[{sender}]: [пососи: файл {filename} сохранён, но пуст]", flush=True)
				return
			
			if actual_size != len(file_data):
				print(f"\n[{sender}]: [предупреждение: размер файла не совпадает. Ожидалось: {len(file_data)}, получено: {actual_size}]", flush=True)
			
			size_mb = file_size / (1024 * 1024)
			size_str = f"{size_mb:.2f} МБ" if size_mb >= 1 else f"{file_size / 1024:.2f} КБ"
			encrypt_indicator = " [зашифрован]" if encrypted else ""
			print(f"\n[{sender}]: отправил файл '{filename}' ({size_str}){encrypt_indicator}", flush=True)
			print(f"  → Сохранен как: {os.path.abspath(save_path)}", flush=True)
			print(f"  → Размер файла: {actual_size} байт", flush=True)
			
		except Exception as e:
			print(f"\n[{sender}]: [ошибка при сохранении файла {filename}: {e}]", flush=True)
			import traceback
			traceback.print_exc()
	
	def send_file(self, file_path, encrypt=None):
		"""
		Отправляет файл на сервер.
		
		Args:
			file_path: Путь к файлу для отправки
			encrypt: Шифровать ли файл
		"""
		if encrypt is None:
			encrypt = self.encrypt_default
		if not self.connected:
			print("\nНе подключено к серверу", flush=True)
			return False
		
		try:
			import os
			import base64
			
			if not os.path.exists(file_path):
				print(f"\nФайл не найден: {file_path}", flush=True)
				return False
			
			with open(file_path, 'rb') as f:
				file_data = f.read()
			
			file_size = len(file_data)
			filename = os.path.basename(file_path)
			
			max_size = 10 * 1024 * 1024
			if file_size > max_size:
				print(f"\nФайл слишком большой (максимум 10 МБ). Размер файла: {file_size / (1024 * 1024):.2f} МБ", flush=True)
				return False
			
			if encrypt:
				if not self.encryption_manager:
					print(f"\n[ОШИБКА] Шифрование включено, но менеджер шифрования не инициализирован", flush=True)
					return False
				try:
					encrypted_base64 = self.encryption_manager.encrypt_bytes(file_data)
					file_message = MessageProtocol.create_file_message(
						self.username,
						filename,
						encrypted_base64,
						file_size,
						encrypted=True
					)
				except Exception as encrypt_error:
					print(f"\n[ОШИБКА] Ошибка шифрования файла: {encrypt_error}", flush=True)
					return False
			else:
				file_data_base64 = base64.b64encode(file_data).decode('utf-8')
				file_message = MessageProtocol.create_file_message(
					self.username,
					filename,
					file_data_base64,
					file_size,
					encrypted=False
				)
			
			message_bytes = file_message.encode('utf-8')
			self.socket.send(message_bytes)
			
			size_mb = file_size / (1024 * 1024)
			size_str = f"{size_mb:.2f} МБ" if size_mb >= 1 else f"{file_size / 1024:.2f} КБ"
			encrypt_indicator = " [зашифровано]" if encrypt else ""
			print(f"\n[Вы]: отправили файл '{filename}' ({size_str}){encrypt_indicator}", flush=True)
			
			return True
			
		except Exception as e:
			print(f"\nОшибка при отправке файла: {e}", flush=True)
			return False
	
	def send_command(self, command):
		"""Отправляет текстовый хуй на сервер."""
		if not self.connected:
			print("Не подключено к серверу", flush=True)
			return False
		try:
			self.socket.send((command + "\n").encode('utf-8'))
			return True
		except Exception as e:
			print(f"Ошибка при отправке команды: {e}", flush=True)
			return False
	
	def send_message(self, text, encrypt=None):
		"""
		Отправляет сообщение на сервер.
		
		Args:
			text: Текст сообщения
			encrypt: Шифровать ли сообщение
		"""
		if encrypt is None:
			encrypt = self.encrypt_default
		if not self.connected:
			print("Не подключено к серверу")
			return False
		
		try:
			if encrypt and self.encryption_manager:
				encrypted_text = self.encryption_manager.encrypt(text)
				message = MessageProtocol.create_text_message(
					self.username,
					encrypted_text,
					encrypted=True
				)
			else:
				message = MessageProtocol.create_text_message(
					self.username,
					text,
					encrypted=False
				)
			
			message_bytes = message.encode('utf-8')
			self.socket.send(message_bytes)
			return True
			
		except socket.error as e:
			print(f"Ошибка при отправке сообщения (socket): {e}")
			self.connected = False
			return False
		except Exception as e:
			print(f"Ошибка при отправке сообщения: {e}")
			self.connected = False
			return False
	
	def disconnect(self):
		"""Отключается от сервера."""
		if self.connected:
			try:
				leave_msg = MessageProtocol.create_leave_message(self.username)
				self.socket.send(leave_msg.encode('utf-8'))
			except:
				pass
		
		self.connected = False
		
		if self.socket:
			try:
				self.socket.close()
			except:
				pass
		
		print("Отключено от сервера")


def run_client_interactive(server_host, server_port, username, password=None):
	"""Запускает интерактивный режим клиента."""
	client = DecentralizedClient(server_host, server_port, username, password)
	
	if not client.connect():
		return
	
	print(f"\nДобро пожаловать, {username}!")
	print("Режим шифрования: включён (AES-256-GCM)")
	print("Введите сообщение (команды: '/online', '/file ПУТЬ', 'exit'):")
	print("-" * 50)
	encrypt_mode = client.encrypt_default
	try:
		while client.connected:
			try:
				if sys.stdin.isatty():
					user_input = input()
				else:
					user_input = sys.stdin.readline().strip()
				
				if not user_input:
					continue
				
				if user_input.lower() == 'exit':
					break
				elif user_input == '/online':
					client.send_command('/online')
					continue
				elif user_input.startswith('/file '):
					file_path = user_input[6:].strip()
					if file_path:
						client.send_file(file_path, encrypt=encrypt_mode)
					else:
						print("Использование: /file ПУТЬ_К_ФАЙЛУ", flush=True)
					continue
				elif user_input.startswith('/'):
					print("Доступные команды: /online, /file ПУТЬ_К_ФАЙЛУ, exit", flush=True)
					continue
				
				if client.send_message(user_input, encrypt=encrypt_mode):
					encrypt_indicator = " [зашифровано]" if encrypt_mode else ""
					print(f"[Вы]: {user_input}{encrypt_indicator}", flush=True)
				
			except EOFError:
				break
			except KeyboardInterrupt:
				break
			except Exception as e:
				print(f"Ошибка: {e}")
				break
	
	except KeyboardInterrupt:
		pass
	finally:
		client.disconnect()


if __name__ == "__main__":
	import sys
	
	if len(sys.argv) < 4:
		print("Использование: python client.py <host> <port> <username> [password]")
		sys.exit(1)
	
	server_host = sys.argv[1]
	server_port = int(sys.argv[2])
	username = sys.argv[3]
	password = sys.argv[4] if len(sys.argv) > 4 else None
	
	run_client_interactive(server_host, server_port, username, password)

