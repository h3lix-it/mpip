import socket
import threading
import select
import time
import json
import sqlite3
from protocol import MessageProtocol
from encryption import EncryptionManager


class DecentralizedServer:
    
    def __init__(self, host='0.0.0.0', port=8888, password=None):
        """
        Инициализация сервера.
        
        Args:
            host: Адрес для прослушивания (0.0.0.0 для всех интерфейсов)
            port: Порт для прослушивания
            password: Пароль для шифрования (опционально)
        """
        self.host = host
        self.port = port
        self.socket = None
        self.clients = {}  # {socket: {...}}
        self.running = False
        self.encryption_manager = EncryptionManager(password) if password else None
        self.shared_password = password
        self.user_db = {}  # {username: password}
        self.server_rooms = set(["main"]) 
        self.user_contacts = {}  # {username: set(contact_names)}
        self._init_db()
        self._load_users_from_db()
        self._load_contacts_from_db()
        self._ensure_chat_tables()
        import os
        try:
            self.avatars_dir = os.path.join(os.getcwd(), 'avatars')
            if not os.path.exists(self.avatars_dir):
                os.makedirs(self.avatars_dir)
        except Exception as e:
            print(f"Avatar dir init error: {e}")
    
    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            
            print(f"Сервер запущен на {self.host}:{self.port}")
            if self.shared_password:
                print(f"Шифрование включено (пароль: {self.shared_password})")
            
            accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            accept_thread.start()
            
            while self.running:
                time.sleep(1)
            
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"Ошибка при запуске сервера: {e}")
            self.stop()
    
    def _accept_connections(self):
        while self.running:
            try:
                if self.socket:
                    client_socket, address = self.socket.accept()
                    print(f"Новое подключение от {address}")
                    
                    self.clients[client_socket] = {
                        'username': None,
                        'address': address,
                        'encryption': None,
                        'authenticated': False,
                        'room': 'main'
                    }
                    
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket,),
                        daemon=True
                    )
                    client_thread.start()
            except OSError:
                break
    
    def _handle_client(self, client_socket):
        buffer = ""
        
        while self.running:
            try:
                ready = select.select([client_socket], [], [], 1.0)
                if not ready[0]:
                    continue
                
                data = client_socket.recv(4096).decode('utf-8', errors='ignore')
                
                if not data:
                    break
                
                buffer += data
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line:
                        lstrip = line.lstrip()
                        if lstrip.startswith('{') and lstrip.endswith('}'):
                            self._process_message(client_socket, line)
                        else:
                            self._process_text_command(client_socket, line.strip())
                        
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"Ошибка при обработке клиента {client_socket.getpeername()}: {e}")
                break
        
        self._disconnect_client(client_socket)
    
    def _process_message(self, client_socket, message_data):
        message = MessageProtocol.parse_message(message_data)
        if not message:
            return
        
        msg_type = message.get('type')
        username = message.get('username')
        
        if msg_type == MessageProtocol.MSG_TYPE_JOIN:
            old_username = self.clients.get(client_socket, {}).get('username')
            self.clients[client_socket]['username'] = username
            
            if self.shared_password:
                encryption = EncryptionManager(self.shared_password)
                self.clients[client_socket]['encryption'] = encryption
            
            self._broadcast(message_data, exclude=client_socket)
            
            self._send_user_list(client_socket)
            
            print(f"Пользователь {username} присоединился")
        
        elif msg_type == MessageProtocol.MSG_TYPE_MESSAGE:
            room = self.clients.get(client_socket, {}).get('room', 'main')
            self._broadcast_room(message_data, room, exclude=None)
            
            content = message.get('content', '')
            try:
                sender = message.get('username') or 'Unknown'
                room = self.clients.get(client_socket, {}).get('room', 'main')
                self._db_add_message(time.time(), sender, content, recipient=None, room=room)
            except Exception:
                pass
            if message.get('encrypted', False):
                try:
                    encryption = self.clients[client_socket].get('encryption')
                    if encryption:
                        content = encryption.decrypt(content)
                        print(f"{username}: [зашифровано -> {content[:50]}...]")
                except:
                    print(f"{username}: [зашифрованное сообщение]")
            else:
                print(f"{username}: {content}")
        
        elif msg_type == MessageProtocol.MSG_TYPE_FILE:
            filename = message.get('filename', 'unknown_file')
            file_size = message.get('file_size', 0)
            encrypted = message.get('encrypted', False)
            
            self._broadcast(message_data, exclude=None)
            
            size_mb = file_size / (1024 * 1024)
            size_str = f"{size_mb:.2f} МБ" if size_mb >= 1 else f"{file_size / 1024:.2f} КБ"
            encrypt_indicator = " [зашифрован]" if encrypted else ""
            print(f"{username}: отправил файл '{filename}' ({size_str}){encrypt_indicator}")
        
        elif msg_type == MessageProtocol.MSG_TYPE_PING:
            pong = MessageProtocol.create_pong_message()
            try:
                client_socket.send(pong.encode('utf-8'))
            except:
                pass
        
        elif msg_type == MessageProtocol.MSG_TYPE_LEAVE:
            self._disconnect_client(client_socket)

    def _send_line(self, client_socket, text: str):
        try:
            client_socket.send((text + "\n").encode('utf-8'))
        except Exception:
            pass

    def _broadcast_text(self, text: str, exclude=None):
        for cs in list(self.clients.keys()):
            if exclude is not None and cs == exclude:
                continue
            self._send_line(cs, text)

    def _process_text_command(self, client_socket, line: str):
        info = self.clients.get(client_socket, {})
        tokens = line.split()
        if not tokens:
            return
        cmd = tokens[0]

        if cmd == '/register' and len(tokens) >= 3:
            user, pwd = tokens[1], ' '.join(tokens[2:])
            if user in self.user_db:
                self._send_line(client_socket, "Username already taken")
                return
            if not self._db_add_user(user, pwd):
                self._send_line(client_socket, "Username already taken")
                return
            self.user_db[user] = pwd
            self._send_line(client_socket, "Registration successful")
            return

        if cmd == '/login' and len(tokens) >= 3:
            user, pwd = tokens[1], ' '.join(tokens[2:])
            if user not in self.user_db or self.user_db[user] != pwd:
                self._send_line(client_socket, "Invalid username or password")
                return
            info['authenticated'] = True
            info['username'] = user
            self.clients[client_socket] = info
            if user not in self.user_contacts:
                self.user_contacts[user] = set()
            self._send_line(client_socket, "Login successful")
            return

        if cmd == '/list_servers':
            servers_str = ", ".join(sorted(self.server_rooms))
            self._send_line(client_socket, f"Servers: {servers_str}")
            return

        if cmd == '/join_server' and len(tokens) >= 2:
            room = tokens[1]
            if room:
                self.server_rooms.add(room)
                info['room'] = room
                self.clients[client_socket] = info
                self._send_line(client_socket, f"Joined server {room}")
                try:
                    servers_str = ", ".join(sorted(self.server_rooms))
                    self._send_line(client_socket, f"Servers: {servers_str}")
                except Exception:
                    pass
            return

        if cmd == '/use' and len(tokens) >= 2:
            room = tokens[1]
            if room in self.server_rooms:
                info['room'] = room
                self.clients[client_socket] = info
                self._send_line(client_socket, f"Using {room}")
            else:
                self._send_line(client_socket, f"No such room {room}")
            return

        if cmd == '/leave':
            info['room'] = 'main'
            self.clients[client_socket] = info
            self._send_line(client_socket, "Using main")
            return

        if cmd == '/pm' and len(tokens) >= 3:
            target = tokens[1]
            msg = line.split(' ', 2)[2]
            sender = info.get('username') or 'Unknown'
            target_socket = None
            for cs, ci in self.clients.items():
                if ci.get('username') == target and ci.get('authenticated'):
                    target_socket = cs
                    break
            if target_socket is not None:
                self._send_line(target_socket, f"(Private) {sender}: {msg}")
                self._send_line(client_socket, f"(Private) {sender}: {msg}")
                try:
                    self._db_add_message(time.time(), sender, msg, recipient=target, room=None)
                except Exception:
                    pass
            else:
                self._send_line(client_socket, f"User {target} not online")
            return

        sender = info.get('username') or 'Unknown'
        room = info.get('room', 'main')
        self._broadcast_text_room(f"{sender}: {line}", room)
        try:
            self._db_add_message(time.time(), sender, line, recipient=None, room=room)
        except Exception:
            pass
        
        if cmd == '/status' and len(tokens) >= 2:
            status_value = tokens[1]
            info['status'] = status_value
            self.clients[client_socket] = info
            self._broadcast_text(f"(Status) {info.get('username') or 'Unknown'}: {status_value}")
            return
        
        if cmd == '/who':
            users = []
            for ci in self.clients.values():
                if ci.get('authenticated') and ci.get('username'):
                    users.append(f"{ci['username']}[{ci.get('status','online')}]")
            self._send_line(client_socket, "Users: " + ", ".join(users))
            return

        if cmd == '/history' and len(tokens) >= 2:
            owner = info.get('username')
            peer = tokens[1]
            try:
                limit = int(tokens[2]) if len(tokens) >= 3 else 50
            except Exception:
                limit = 50
            if not owner:
                self._send_line(client_socket, "Error: not authenticated")
                return
            try:
                cur = self.db.cursor()
                cur.execute(
                    'SELECT ts, sender, recipient, content FROM messages\n'
                    ' WHERE (sender=? AND recipient=?) OR (sender=? AND recipient=?)\n'
                    ' ORDER BY ts DESC LIMIT ?\n', (owner, peer, peer, owner, limit))
                rows = cur.fetchall()[::-1]
                for ts, sender, recipient, content in rows:
                    safe = content.replace('\n', ' ')
                    self._send_line(client_socket, f"HIST {sender}: {safe}")
            except Exception as e:
                self._send_line(client_socket, f"Error: history failed")
            return

        if cmd == '/history_room' and len(tokens) >= 2:
            room = tokens[1]
            try:
                limit = int(tokens[2]) if len(tokens) >= 3 else 50
            except Exception:
                limit = 50
            try:
                cur = self.db.cursor()
                cur.execute(
                    'SELECT ts, sender, content FROM messages\n'
                    ' WHERE room=? ORDER BY ts DESC LIMIT ?\n', (room, limit))
                rows = cur.fetchall()[::-1]
                for ts, sender, content in rows:
                    safe = content.replace('\n', ' ')
                    self._send_line(client_socket, f"HIST_ROOM {room} {sender}: {safe}")
            except Exception:
                self._send_line(client_socket, "Error: history_room failed")
            return

        if cmd == '/set_avatar' and len(tokens) >= 3:
            user = info.get('username')
            if not user:
                self._send_line(client_socket, "Error: not authenticated")
                return
            mime = tokens[1]
            try:
                b64 = line.split(' ', 2)[2]
            except Exception:
                b64 = ''
            try:
                import base64
                data = base64.b64decode(b64)
                ok = self._fs_set_avatar(user, mime, data)
                try:
                    self._db_set_avatar(user, mime, data)
                except Exception:
                    pass
                self._send_line(client_socket, "AVATAR_OK" if ok else "AVATAR_ERR")
            except Exception:
                self._send_line(client_socket, "AVATAR_ERR")
            return

        if cmd == '/get_avatar' and len(tokens) >= 2:
            target = tokens[1]
            try:
                av = self._fs_get_avatar(target)
                if av is None:
                    self._send_line(client_socket, "AVATAR_NONE")
                else:
                    mime, data = av
                    import base64
                    b64 = base64.b64encode(data).decode('ascii')
                    self._send_line(client_socket, f"AVATAR {target} {mime} {b64}")
            except Exception:
                self._send_line(client_socket, "AVATAR_ERR")
            return

        if cmd == '/search' and len(tokens) >= 2:
            term = ' '.join(tokens[1:]).lower()
            found = []
            for uname in self.user_db.keys():
                if term in uname.lower():
                    status = 'offline'
                    for ci in self.clients.values():
                        if ci.get('username') == uname and ci.get('authenticated'):
                            status = ci.get('status', 'online')
                            break
                    found.append(f"{uname}[{status}]")
            self._send_line(client_socket, "Users: " + ", ".join(found))
            return

        if cmd == '/add_contact' and len(tokens) >= 2:
            owner = info.get('username')
            target = tokens[1]
            if not owner:
                self._send_line(client_socket, "Error: not authenticated")
                return
            if owner == target:
                self._send_line(client_socket, "Error: cannot add yourself")
                return
            try:
                cur = self.db.cursor()
                cur.execute('SELECT 1 FROM contacts WHERE owner=? AND contact=?', (owner, target))
                if cur.fetchone():
                    self._send_line(client_socket, f"Already in contacts: {target}")
                    return
                cur.execute('SELECT status FROM friend_requests WHERE (from_user=? AND to_user=?) OR (from_user=? AND to_user=?) ORDER BY id DESC LIMIT 1', (owner, target, target, owner))
                row = cur.fetchone()
                if row and row[0] == 'pending':
                    self._send_line(client_socket, "Request already pending")
                    return
                cur.execute('INSERT INTO friend_requests(from_user, to_user, status) VALUES(?,?,"pending")', (owner, target))
                self.db.commit()
                self._send_line(client_socket, f"REQUEST_SENT {target}")
                for cs, ci in self.clients.items():
                    if ci.get('authenticated') and ci.get('username') == target:
                        self._send_line(cs, f"REQUEST from {owner}")
                        break
            except Exception:
                self._send_line(client_socket, "Error: request failed")
            return

        if cmd == '/accept' and len(tokens) >= 2:
            me = info.get('username')
            other = tokens[1]
            if not me:
                self._send_line(client_socket, "Error: not authenticated")
                return
            try:
                cur = self.db.cursor()
                cur.execute('SELECT id FROM friend_requests WHERE from_user=? AND to_user=? AND status="pending" ORDER BY id DESC LIMIT 1', (other, me))
                row = cur.fetchone()
                if not row:
                    self._send_line(client_socket, "No pending request from this user")
                    return
                req_id = row[0]
                cur.execute('UPDATE friend_requests SET status="accepted" WHERE id=?', (req_id,))
                self._db_add_contact(me, other)
                self._db_add_contact(other, me)
                if me not in self.user_contacts:
                    self.user_contacts[me] = set()
                if other not in self.user_contacts:
                    self.user_contacts[other] = set()
                self.user_contacts[me].add(other)
                self.user_contacts[other].add(me)
                self.db.commit()
                self._send_line(client_socket, f"REQUEST_ACCEPTED {other}")
                for cs, ci in self.clients.items():
                    if ci.get('authenticated') and ci.get('username') == other:
                        self._send_line(cs, f"REQUEST_ACCEPTED {me}")
                        break
            except Exception:
                self._send_line(client_socket, "Error: accept failed")
            return

        if cmd == '/decline' and len(tokens) >= 2:
            me = info.get('username')
            other = tokens[1]
            if not me:
                self._send_line(client_socket, "Error: not authenticated")
                return
            try:
                cur = self.db.cursor()
                cur.execute('SELECT id FROM friend_requests WHERE from_user=? AND to_user=? AND status="pending" ORDER BY id DESC LIMIT 1', (other, me))
                row = cur.fetchone()
                if not row:
                    self._send_line(client_socket, "No pending request from this user")
                    return
                req_id = row[0]
                cur.execute('UPDATE friend_requests SET status="declined" WHERE id=?', (req_id,))
                self.db.commit()
                self._send_line(client_socket, f"REQUEST_DECLINED {other}")
                for cs, ci in self.clients.items():
                    if ci.get('authenticated') and ci.get('username') == other:
                        self._send_line(cs, f"REQUEST_DECLINED {me}")
                        break
            except Exception:
                self._send_line(client_socket, "Error: decline failed")
            return

        if cmd == '/list_requests':
            me = info.get('username')
            if not me:
                self._send_line(client_socket, "Error: not authenticated")
                return
            try:
                cur = self.db.cursor()
                cur.execute('SELECT from_user FROM friend_requests WHERE to_user=? AND status="pending" ORDER BY id DESC', (me,))
                users = [r[0] for r in cur.fetchall()]
                self._send_line(client_socket, "Requests: " + ", ".join(users))
            except Exception:
                self._send_line(client_socket, "Error: list_requests failed")
            return

        if cmd == '/list_contacts':
            owner = info.get('username')
            contacts = sorted(self.user_contacts.get(owner, set())) if owner else []
            self._send_line(client_socket, "Contacts: " + ", ".join(contacts))
            return

    def _init_db(self):
        try:
            self.db = sqlite3.connect('server.db', check_same_thread=False)
            cur = self.db.cursor()
            cur.execute(
                'CREATE TABLE IF NOT EXISTS users (\n'
                '  username TEXT PRIMARY KEY,\n'
                '  password TEXT NOT NULL\n'
                ')'
            )
            cur.execute(
                'CREATE TABLE IF NOT EXISTS contacts (\n'
                '  owner TEXT NOT NULL,\n'
                '  contact TEXT NOT NULL,\n'
                '  PRIMARY KEY(owner, contact)\n'
                ')'
            )
            cur.execute(
                'CREATE TABLE IF NOT EXISTS friend_requests (\n'
                '  id INTEGER PRIMARY KEY AUTOINCREMENT,\n'
                '  from_user TEXT NOT NULL,\n'
                '  to_user TEXT NOT NULL,\n'
                '  status TEXT NOT NULL DEFAULT "pending"\n'
                ')'
            )
            self.db.commit()
        except Exception as e:
            print(f"DB init error: {e}")

    def _load_users_from_db(self):
        try:
            cur = self.db.cursor()
            cur.execute('SELECT username, password FROM users')
            for u, p in cur.fetchall():
                self.user_db[u] = p
        except Exception as e:
            print(f"DB load users error: {e}")

    def _load_contacts_from_db(self):
        try:
            cur = self.db.cursor()
            cur.execute('SELECT owner, contact FROM contacts')
            rows = cur.fetchall()
            for owner, contact in rows:
                if owner not in self.user_contacts:
                    self.user_contacts[owner] = set()
                self.user_contacts[owner].add(contact)
        except Exception as e:
            print(f"DB load contacts error: {e}")

    def _ensure_chat_tables(self):
        try:
            cur = self.db.cursor()
            cur.execute(
                'CREATE TABLE IF NOT EXISTS messages (\n'
                '  id INTEGER PRIMARY KEY AUTOINCREMENT,\n'
                '  ts REAL NOT NULL,\n'
                '  sender TEXT NOT NULL,\n'
                '  recipient TEXT,\n'
                '  room TEXT,\n'
                '  content TEXT NOT NULL\n'
                ')'
            )
            cur.execute(
                'CREATE TABLE IF NOT EXISTS avatars (\n'
                '  username TEXT PRIMARY KEY,\n'
                '  mime TEXT,\n'
                '  data BLOB\n'
                ')'
            )
            self.db.commit()
        except Exception as e:
            print(f"DB ensure chat tables error: {e}")

    def _db_add_message(self, ts: float, sender: str, content: str, recipient: str = None, room: str = None):
        try:
            cur = self.db.cursor()
            cur.execute('INSERT INTO messages(ts, sender, recipient, room, content) VALUES(?,?,?,?,?)', (ts, sender, recipient, room, content))
            self.db.commit()
        except Exception as e:
            print(f"DB add message error: {e}")

    def _db_set_avatar(self, username: str, mime: str, data: bytes) -> bool:
        try:
            cur = self.db.cursor()
            cur.execute('INSERT OR REPLACE INTO avatars(username, mime, data) VALUES(?,?,?)', (username, mime, sqlite3.Binary(data)))
            self.db.commit()
            return True
        except Exception as e:
            print(f"DB set avatar error: {e}")
            return False

    def _db_get_avatar(self, username: str):
        try:
            cur = self.db.cursor()
            cur.execute('SELECT mime, data FROM avatars WHERE username=?', (username,))
            row = cur.fetchone()
            if row:
                return row[0], row[1]
        except Exception as e:
            print(f"DB get avatar error: {e}")
        return None

    def _fs_ext_from_mime(self, mime: str) -> str:
        if 'png' in mime:
            return '.png'
        if 'gif' in mime:
            return '.gif'
        return '.jpg'

    def _fs_set_avatar(self, username: str, mime: str, data: bytes) -> bool:
        try:
            import os
            ext = self._fs_ext_from_mime(mime)
            path = os.path.join(self.avatars_dir, f"{username}{ext}")
            with open(path, 'wb') as f:
                f.write(data)
            return True
        except Exception as e:
            print(f"FS set avatar error: {e}")
            return False

    def _fs_get_avatar(self, username: str):
        try:
            import os
            for ext, mime in [('.png','image/png'),('.gif','image/gif'),('.jpg','image/jpeg'),('.jpeg','image/jpeg')]:
                path = os.path.join(self.avatars_dir, f"{username}{ext}")
                if os.path.exists(path):
                    with open(path, 'rb') as f:
                        data = f.read()
                    if mime not in ('image/png','image/gif'):
                        try:
                            from PIL import Image
                            import io
                            img = Image.open(io.BytesIO(data))
                            out = io.BytesIO()
                            w, h = img.size
                            if w > 96:
                                nh = int(h * (float(96) / float(w)))
                                img = img.resize((96, nh), Image.LANCZOS)
                            img.save(out, format='PNG')
                            data = out.getvalue()
                            mime = 'image/png'
                        except Exception:
                            pass
                    return mime, data
        except Exception as e:
            print(f"FS get avatar error: {e}")
        return None

    def _db_add_user(self, username: str, password: str) -> bool:
        try:
            cur = self.db.cursor()
            cur.execute('INSERT INTO users(username, password) VALUES(?, ?)', (username, password))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            print(f"DB add user error: {e}")
            return False

    def _db_add_contact(self, owner: str, contact: str) -> bool:
        try:
            cur = self.db.cursor()
            cur.execute('INSERT OR IGNORE INTO contacts(owner, contact) VALUES(?, ?)', (owner, contact))
            self.db.commit()
            return True
        except Exception as e:
            print(f"DB add contact error: {e}")
            return False
    
    def _broadcast(self, message, exclude=None):
        """Отправляет сообщение всем подключенным клиентам, кроме указанного."""
        disconnected = []
        
        message_bytes = message.encode('utf-8') if isinstance(message, str) else message
        
        for client_socket in list(self.clients.keys()):
            if exclude is not None and client_socket == exclude:
                continue
            
            try:
                sent = client_socket.send(message_bytes)
                if sent < len(message_bytes):
                    remaining = message_bytes[sent:]
                    while remaining:
                        sent = client_socket.send(remaining)
                        remaining = remaining[sent:]
            except (ConnectionResetError, BrokenPipeError, OSError):
                disconnected.append(client_socket)
            except Exception as e:
                username = self.clients.get(client_socket, {}).get('username', 'неизвестно')
                print(f"Ошибка при отправке сообщения клиенту {username}: {e}")
                disconnected.append(client_socket)
        
        for client_socket in disconnected:
            self._disconnect_client(client_socket, notify=False)

    def _broadcast_room(self, message, room: str, exclude=None):
        disconnected = []
        message_bytes = message.encode('utf-8') if isinstance(message, str) else message
        for cs, ci in list(self.clients.items()):
            if ci.get('room') != room:
                continue
            if exclude is not None and cs == exclude:
                continue
            try:
                sent = cs.send(message_bytes)
                if sent < len(message_bytes):
                    remaining = message_bytes[sent:]
                    while remaining:
                        sent = cs.send(remaining)
                        remaining = remaining[sent:]
            except (ConnectionResetError, BrokenPipeError, OSError):
                disconnected.append(cs)
            except Exception:
                disconnected.append(cs)
        for cs in disconnected:
            self._disconnect_client(cs, notify=False)

    def _broadcast_text_room(self, text: str, room: str, exclude=None):
        self._broadcast_room(text + "\n", room, exclude)
    
    def _send_user_list(self, client_socket):
        user_list = [
            info['username'] 
            for info in self.clients.values() 
            if info['username']
        ]
        
        message = MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_USER_LIST,
            json.dumps(user_list)
        )
        
        try:
            client_socket.send(message.encode('utf-8'))
        except:
            pass
    
    def _disconnect_client(self, client_socket, notify=True):
        """Отключает клиента и уведомляет остальных."""
        client_info = self.clients.get(client_socket)
        
        if client_info and client_info.get('username') and notify:
            leave_msg = MessageProtocol.create_leave_message(client_info['username'])
            self._broadcast(leave_msg, exclude=client_socket)
            print(f"Пользователь {client_info['username']} отключился")
        
        if client_socket in self.clients:
            del self.clients[client_socket]
        
        try:
            client_socket.close()
        except:
            pass
    
    def stop(self):
        """Останавливает сервер."""
        self.running = False
        
        for client_socket in list(self.clients.keys()):
            self._disconnect_client(client_socket, notify=False)
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        
        print("Сервер остановлен")


if __name__ == "__main__":
    import sys
    
    host = '0.0.0.0'
    port = 8888
    password = None
    
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        password = sys.argv[2]
    
    server = DecentralizedServer(host=host, port=port, password=password)
    
    try:
        server.start()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        server.stop()

