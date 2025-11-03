"""
Клиент для подключения к децентрализованному серверу обмена сообщениями.
Может подключаться к любому серверу в сети.
"""
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
        self.encryption_manager = EncryptionManager(password) if password else None
        self.shared_password = password
        self.users = []
    
    def connect(self):
        """Подключается к серверу."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_host, self.server_port))
            self.connected = True
            
            print(f"Подключено к серверу {self.server_host}:{self.server_port}")
            
            join_msg = MessageProtocol.create_join_message(self.username)
            self.socket.send(join_msg.encode('utf-8'))
            
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
                data = self.socket.recv(4096).decode('utf-8', errors='ignore')
                
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
                                buffer = ''  # Очищаем буфер после обработки
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
                # Если не удалось распарсить, игнорируем (может быть неполное сообщение)
                return
            
            msg_type = message.get('type')
            content = message.get('content', '')
            sender = message.get('username', 'Система')
            
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
                if self.encryption_manager:
                    decrypted_base64 = self.encryption_manager.decrypt(file_data_base64)
                    file_data = base64.b64decode(decrypted_base64)
                else:
                    print(f"\n[{sender}]: [файл {filename} зашифрован - нет ключа]", flush=True)
                    return
            else:
                file_data = base64.b64decode(file_data_base64)
            
            downloads_dir = "downloads"
            if not os.path.exists(downloads_dir):
                os.makedirs(downloads_dir)
            
            import time
            safe_filename = os.path.basename(filename)
            timestamp = int(time.time())
            save_path = os.path.join(downloads_dir, f"{timestamp}_{safe_filename}")
            
            with open(save_path, 'wb') as f:
                f.write(file_data)
            
            size_mb = file_size / (1024 * 1024)
            size_str = f"{size_mb:.2f} МБ" if size_mb >= 1 else f"{file_size / 1024:.2f} КБ"
            print(f"\n[{sender}]: отправил файл '{filename}' ({size_str})", flush=True)
            print(f"  → Сохранен как: {save_path}", flush=True)
            
        except Exception as e:
            print(f"\n[{sender}]: [ошибка при сохранении файла {filename}: {e}]", flush=True)
    
    def send_file(self, file_path, encrypt=False):
        """
        Отправляет файл на сервер.
        
        Args:
            file_path: Путь к файлу для отправки
            encrypt: Шифровать ли файл
        """
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
            
            max_size = 10 * 1024 * 1024  # 10 МБ
            if file_size > max_size:
                print(f"\nФайл слишком большой (максимум 10 МБ). Размер файла: {file_size / (1024 * 1024):.2f} МБ", flush=True)
                return False
            
            file_data_base64 = base64.b64encode(file_data).decode('utf-8')
            
            if encrypt and self.encryption_manager:
                encrypted_base64 = self.encryption_manager.encrypt(file_data_base64)
                file_message = MessageProtocol.create_file_message(
                    self.username,
                    filename,
                    encrypted_base64,
                    file_size,
                    encrypted=True
                )
            else:
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
    
    def send_message(self, text, encrypt=False):
        """
        Отправляет сообщение на сервер.
        
        Args:
            text: Текст сообщения
            encrypt: Шифровать ли сообщение
        """
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
    print("Введите сообщение (или 'exit' для выхода, '/encrypt' для шифрования, '/file путь' для отправки файла):")
    print("-" * 50)
    
    encrypt_mode = False
    
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
                elif user_input == '/encrypt':
                    encrypt_mode = not encrypt_mode
                    status = "включено" if encrypt_mode else "выключено"
                    print(f"Шифрование: {status}", flush=True)
                    continue
                elif user_input.startswith('/file '):
                    file_path = user_input[6:].strip()
                    if file_path:
                        client.send_file(file_path, encrypt=encrypt_mode)
                    else:
                        print("Использование: /file путь_к_файлу", flush=True)
                    continue
                elif user_input.startswith('/'):
                    print("Доступные команды: /encrypt, /file путь_к_файлу, exit", flush=True)
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
        print("Использование: python client.py <host> <port> <username> [password] ([сколько см] [cvv банковской карты] [номер банковской карты])")
        sys.exit(1)
    
    server_host = sys.argv[1]
    server_port = int(sys.argv[2])
    username = sys.argv[3]
    password = sys.argv[4] if len(sys.argv) > 4 else None
    
    run_client_interactive(server_host, server_port, username, password)


