"""
ЫЫЫЫЫ
"""
import sys
import argparse
from server import DecentralizedServer
from client import run_client_interactive


def run_server(host='0.0.0.0', port=8888, password=None):
    """Запускает сервер."""
    server = DecentralizedServer(host=host, port=port, password=password)
    
    try:
        print("Запуск сервера...")
        print(f"Адрес: {host}:{port}")
        if password:
            print(f"Шифрование: включено (пароль: {password})")
        print("Нажмите Ctrl+C для остановки\n")
        
        server.start()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
        server.stop()
    except Exception as e:
        print(f"Ошибка: {e}")
        server.stop()


def run_client(server_host=None, server_port=None, username=None, password=None):
    """Запускает клиент."""
    try:
        print("MPIP GitHub: https://github.com/h3lix-it/mpip", flush=True)
        print("=== Подключение к серверу ===")
        
        if not server_host:
            server_host = input("Адрес сервера (localhost): ").strip() or "localhost"
        else:
            print(f"Адрес сервера: {server_host}")
        
        if not server_port:
            port_input = input("Порт сервера (8888): ").strip() or "8888"
            try:
                server_port = int(port_input)
            except ValueError:
                print("Неверный порт, используется 8888")
                server_port = 8888
        else:
            print(f"Порт сервера: {server_port}")
        
        if not username:
            username = input("Ваш никнейм: ").strip()
            if not username:
                print("Никнейм не может быть пустым!")
                return
        
        if not password:
            password_input = input("Пароль (Enter для пропуска): ").strip()
            if password_input:
                password = password_input
        
        print()
        run_client_interactive(server_host, server_port, username, password)
    except KeyboardInterrupt:
        print("\nОтмена подключения...")
    except Exception as e:
        print(f"Ошибка: {e}")


def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(
        description='Децентрализованный мессенджер (писанный IlyaYuki и Zhuzhun3000)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  Запуск сервера:
    python main.py server --port 8888
    python main.py server --port 8888 --password secret

  Подключение как клиент:
    python main.py client --host localhost --port 8888 --username Имя
    python main.py client --host localhost --port 8888 --username Имя --password secret
        """
    )
    
    subparsers = parser.add_subparsers(dest='mode', help='Режим работы')
    
    server_parser = subparsers.add_parser('server', help='Запустить сервер')
    server_parser.add_argument('--host', default='0.0.0.0', help='Адрес для прослушивания (по умолчанию: 0.0.0.0)')
    server_parser.add_argument('--port', type=int, default=8888, help='Порт для прослушивания (по умолчанию: 8888)')
    server_parser.add_argument('--password', help='Пароль для шифрования (опционально)')
    
    client_parser = subparsers.add_parser('client', help='Подключиться как клиент')
    client_parser.add_argument('--host', required=True, help='Адрес сервера')
    client_parser.add_argument('--port', type=int, required=True, help='Порт сервера')
    client_parser.add_argument('--username', required=True, help='Имя пользователя')
    client_parser.add_argument('--password', help='Пароль для шифрования (опционально)')
    
    args = parser.parse_args()
    
    if not args.mode:
        print("=== Подключение к серверу ===")
        print()
        run_client()
    
    elif args.mode == 'server':
        run_server(host=args.host, port=args.port, password=args.password)
    elif args.mode == 'client':
        run_client(
            server_host=args.host,
            server_port=args.port,
            username=args.username,
            password=args.password
        )


if __name__ == "__main__":
    main()

