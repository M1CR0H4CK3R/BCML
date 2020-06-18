import os
import requests
import socket
import sys
from pathlib import Path
from platform import system
from subprocess import run
from tempfile import mkdtemp

import webview
from bcml import util


def listen():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", 6666))
        except socket.error:
            send_arg(sock)
            os._exit(0)
        sock.listen()
        while True:
            conn, _ = sock.accept()
            with conn:
                while True:
                    try:
                        data = conn.recv(1024)
                    except ConnectionResetError:
                        break
                    if not data or data == b".":
                        break
                    process_arg(data.decode("utf8"))


def send_arg(sock):
    sock.connect(("127.0.0.1", 6666))
    sock.sendall(sys.argv[1].encode("utf8"))


def process_arg(arg: str = None):
    if not arg:
        if len(sys.argv) < 2:
            return
        arg = sys.argv[1]
    path: Path
    try:
        assert Path(arg).exists()
        path = Path(arg)
    except (ValueError, AssertionError, OSError):
        if not arg.startswith("bcml:"):
            return
        url = arg[5:]
        filename: str = "GameBanana1Click"
        if "," in url:
            url, mod_type, mod_id = url.split(",")
            try:
                res = requests.get(
                    "https://api.gamebanana.com/Core/Item/Data"
                    f"?itemtype={mod_type}&itemid={mod_id}&fields=name"
                )
                filename = util.get_safe_pathname(res.json()[0])
            except (
                requests.ConnectionError,
                requests.RequestException,
                ValueError,
                IndexError,
            ):
                pass
        path = Path(mkdtemp()) / f"{filename}.bnp"
        try:
            res: requests.Response = requests.get(url)
            with path.open("wb") as tmp_file:
                for chunk in res.iter_content(chunk_size=1024):
                    tmp_file.write(chunk)
        except (
            FileNotFoundError,
            PermissionError,
            OSError,
            requests.ConnectionError,
            requests.RequestException,
        ) as e:
            print(e)
            return
    webview.windows[0].evaluate_js(
        f'setTimeout(() => window.oneClick("{path.resolve().as_posix()}"), 500)'
    )


def register_handlers():
    if system() == "Windows":
        _win_create_handler()
    else:
        _linux_create_handler()


def _linux_create_handler():
    schema_file = (
        Path.home() / ".local" / "share" / "applications" / "bcml-schema.desktop"
    )
    if schema_file.exists():
        return
    desktop = f"""
    [Desktop Entry]
    Type=Application
    Name=BCML Schema Handler
    Exec={sys.executable} -m bcml %u
    StartupNotify=false
    MimeType=x-schema-handler/bcml;
    """
    schema_file.write_text(desktop)
    run(f"xdg-mime default '{schema_file.as_posix()}' x-scheme-handler/bcml".split())


def _win_create_handler():
    import winreg

    if (util.get_exec_dir().parent.parent.parent / "Scripts" / "bcml.exe").exists():
        exec_path = (
            '"'
            + str(
                (
                    util.get_exec_dir().parent.parent.parent / "Scripts" / "bcml.exe"
                ).resolve()
            )
            + '"'
        )
    elif (util.get_exec_dir().parent.parent / "bin" / "bcml.exe").exists():
        exec_path = (
            '"'
            + str((util.get_exec_dir().parent.parent / "bin" / "bcml.exe").resolve())
            + '"'
        )
    else:
        exec_path = f'"{sys.executable}" -m bcml'

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\bcml") as key:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\bcml\shell\open\command",
                0,
                winreg.KEY_READ,
            ) as okey:
                assert exec_path in winreg.QueryValueEx(okey, "")[0]
        except (WindowsError, OSError, AssertionError):
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(key, r"shell\open\command") as key2:
                winreg.SetValueEx(key2, "", 0, winreg.REG_SZ, f'{exec_path} "%1"')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.bnp") as key:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Classes\.bnp", 0, winreg.KEY_READ,
            ) as okey:
                assert winreg.QueryValueEx(okey, "")[0] == "bcml"
        except (WindowsError, OSError, AssertionError):
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "bcml")