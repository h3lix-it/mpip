import json
import time


class MessageProtocol:
    
    MSG_TYPE_MESSAGE = "MESSAGE"
    MSG_TYPE_FILE = "FILE"
    MSG_TYPE_JOIN = "JOIN"
    MSG_TYPE_LEAVE = "LEAVE"
    MSG_TYPE_PING = "PING"
    MSG_TYPE_PONG = "PONG"
    MSG_TYPE_KEY_EXCHANGE = "KEY_EXCHANGE"
    MSG_TYPE_USER_LIST = "USER_LIST"
    
    @staticmethod
    def create_message(msg_type, content, username=None, encrypted=False):
        message = {
            "type": msg_type,
            "content": content,
            "timestamp": time.time(),
            "encrypted": encrypted
        }
        
        if username:
            message["username"] = username
        
        return json.dumps(message) + "\n"
    
    @staticmethod
    def parse_message(data):
        try:
            return json.loads(data.strip())
        except (json.JSONDecodeError, AttributeError):
            return None
    
    @staticmethod
    def create_text_message(username, text, encrypted=False):
        return MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_MESSAGE,
            text,
            username,
            encrypted
        )
    
    @staticmethod
    def create_join_message(username):
        return MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_JOIN,
            f"{username} присоединился к чату",
            username
        )
    
    @staticmethod
    def create_leave_message(username):
        return MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_LEAVE,
            f"{username} покинул чат",
            username
        )
    
    @staticmethod
    def create_ping_message():
        return MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_PING,
            ""
        )
    
    @staticmethod
    def create_pong_message():
        return MessageProtocol.create_message(
            MessageProtocol.MSG_TYPE_PONG,
            ""
        )
    
    @staticmethod
    def create_file_message(username, filename, file_data_base64, file_size, encrypted=False):
        import base64
        message = {
            "type": MessageProtocol.MSG_TYPE_FILE,
            "filename": filename,
            "file_data": file_data_base64,
            "file_size": file_size,
            "timestamp": time.time(),
            "encrypted": encrypted
        }
        
        if username:
            message["username"] = username
        
        return json.dumps(message) + "\n"

