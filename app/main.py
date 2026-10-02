import ctypes
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from urllib.parse import (urlencode, urlparse, parse_qs)
from urllib.request import (ProxyHandler, Request, build_opener)
import winreg
BUNDLE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CodexChineseProxy'
SERVER_URL = 'http://154.201.74.158:8765'
REG_PATH = 'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
DIRECT = build_opener(ProxyHandler({}))

def get_key_info(key):
    url = SERVER_URL + '/check?' + urlencode({'key': key.strip()})
    with DIRECT.open(url, timeout=10) as response:
        return json.load(response)

def verify_key(key):
    return get_key_info(key).get('ok') is True

def make_config(link, port):
    u = urlparse(link.strip())
    q = parse_qs(u.query)
    def value(name, default=''):
        return q.get(name, [default])[0]

    if u.scheme != 'vless' or not u.hostname or not u.username:
        raise ValueError('内置节点配置无效')
    return {'log': {'loglevel': 'warning'}, 'inbounds': [{'listen': '127.0.0.1', 'port': port, 'protocol': 'http'}], 'outbounds': [{'protocol': 'vless', 'settings': {'vnext': [{'address': u.hostname, 'port': u.port or 443, 'users': [{'id': u.username, 'encryption': 'none', 'flow': value('flow')}]}]}, 'streamSettings': {'network': 'tcp', 'security': 'reality', 'realitySettings': {'serverName': value('sni'), 'fingerprint': value('fp', 'chrome'), 'password': value('pbk'), 'shortId': value('sid'), 'spiderX': value('spx')}}}]}

def notify_windows():
    ctypes.windll.Wininet.InternetSetOptionW(None, 39, None, 0)
    ctypes.windll.Wininet.InternetSetOptionW(None, 37, None, 0)

class Proxy:
    def __init__(self):
        self.process = self.log = None
        self.backup = DATA / 'proxy-backup.json'

    def restore(self):
        if not self.backup.exists():
            return
        saved = json.loads(self.backup.read_text(encoding='utf-8'))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            for name, entry in saved.items():
                if entry is None:
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        continue
                else:
                    winreg.SetValueEx(key, name, 0, entry[1], entry[0])
        notify_windows()
        self.backup.unlink()

    def enable_system_proxy(self, port):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            saved = {}
            for name in ('ProxyEnable', 'ProxyServer', 'ProxyOverride', 'AutoConfigURL'):
                try:
                    saved[name] = list(winreg.QueryValueEx(key, name))
                except FileNotFoundError:
                    saved[name] = None
                    continue
            self.backup.write_text(json.dumps(saved), encoding='utf-8')
            winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'127.0.0.1:{port}')
            winreg.SetValueEx(key, 'ProxyOverride', 0, winreg.REG_SZ, 'localhost;127.*;<local>')
            winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
            try:
                winreg.DeleteValue(key, 'AutoConfigURL')
            except FileNotFoundError:
                pass
        notify_windows()

    def start(self, apply_system=True):
        DATA.mkdir(parents=True, exist_ok=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        executable = BUNDLE / 'vendor' / 'xray' / 'xray.exe'
        link = (BUNDLE / 'node.txt').read_text(encoding='utf-8').strip()
        config = json.dumps(make_config(link, port)).encode('utf-8')
        self.log = (DATA / 'proxy.log').open('ab')
        try:
            self.process = subprocess.Popen([str(executable), 'run', '-c', 'stdin:'], stdin=subprocess.PIPE, stdout=self.log, stderr=self.log, creationflags=subprocess.CREATE_NO_WINDOW)
            self.process.stdin.write(config)
            self.process.stdin.close()
            for _ in range(60):
                if self.process.poll() is not None:
                    raise RuntimeError('代理组件启动失败，请查看本地 proxy.log')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                        pass
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('等待代理组件启动超时')
            endpoint = f'http://127.0.0.1:{port}'
            opener = build_opener(ProxyHandler({'http': endpoint, 'https': endpoint}))
            with opener.open(Request('https://www.microsoft.com/', method='HEAD'), timeout=20) as r:
                if r.status >= 400:
                    raise RuntimeError('代理网络测试未通过')
        except Exception:
            self.stop()
            raise
        try:
            if apply_system:
                self.enable_system_proxy(port)
                return
        except Exception:
            self.stop()
            raise

    def stop(self):
        try:
            self.restore()
        except:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.process = None
        if self.log:
            self.log.close()
            self.log = None


class App:
    def __init__(self, root):
        self.root = root
        self.proxy = Proxy()
        self.events = queue.Queue()
        self.busy = self.active = False
        self.next_check, self.checking = 0, False
        root.title('Codex 中文汉化工具')
        root.geometry('490x330')
        root.resizable(False, False)
        tk.Label(root, text='Codex 中文汉化工具', font=('Microsoft YaHei', 18, 'bold')).pack(pady=16)
        tk.Label(root, text='请输入管理员发放的密钥').pack()
        self.key = tk.Entry(root, width=40, show='•')
        self.key.pack(pady=12)
        self.start_button = tk.Button(root, text='开启汉化', width=28, height=2, command=self.start)
        self.start_button.pack()
        self.stop_button = tk.Button(root, text='关闭', command=self.stop, state='disabled')
        self.stop_button.pack(pady=10)
        self.key_url = 'https://wzyp.cn/item/y734bo'
        link_row = tk.Frame(root)
        link_row.pack()
        tk.Label(link_row, text='获取汉化密钥：').pack(side='left')
        self.key_link = tk.Entry(link_row, width=len(self.key_url) + 1, fg='#0563c1', readonlybackground=root.cget('bg'), relief='flat', bd=0, cursor='hand2', takefocus=True, justify='left')
        self.key_link.insert(0, self.key_url)
        self.key_link.config(state='readonly')
        self.key_link.pack(side='left')
        self.key_link.bind('<ButtonPress-1>', self.link_press)
        self.key_link.bind('<ButtonRelease-1>', self.link_release)
        self.key_link.bind('<Return>', self.open_key_url)
        self.link_menu = tk.Menu(root, tearoff=False)
        self.link_menu.add_command(label='复制链接', command=self.copy_key_url)
        self.key_link.bind('<Button-3>', self.show_link_menu)
        self.status = tk.StringVar(value='')
        tk.Label(root, textvariable=self.status, wraplength=455).pack()
        tk.Label(root, text='汉化成功后大退重启Codex生效', fg='#666666').pack(pady=8)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.proxy.restore()
        root.after(200, self.poll)

    def open_key_url(self, event=None):
        try:
            webbrowser.open_new_tab(self.key_url)
        except Exception as error:
            messagebox.showerror('打开链接失败', str(error))
        return 'break'

    def link_press(self, event):
        self.link_press_x = event.x
        self.link_press_y = event.y

    def link_release(self, event):
        if abs(event.x - self.link_press_x) <= 2 and abs(event.y - self.link_press_y) <= 2:
            self.open_key_url(event)

    def copy_key_url(self, event=None):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.key_url)
        self.root.update_idletasks()
        return 'break'

    def show_link_menu(self, event):
        self.key_link.focus_set()
        try:
            self.link_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.link_menu.grab_release()

    def start(self):
        key = self.key.get().strip()
        if not key:
            messagebox.showerror('请输入密钥', '请输入管理员发放的密钥。')
            return
        self.busy = True
        self.start_button.config(state='disabled')
        self.status.set('正在验证密钥并测试代理，请稍候……')
        def worker():
            try:
                info = get_key_info(key)
                if info.get('ok') is not True:
                    raise RuntimeError('密钥无效或已过期，请联系管理员。')
                self.proxy.start()
                self.events.put(('started', (key, info)))
            except Exception as e:
                self.events.put(('error', str(e)))
                return

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'started':
                    self.active, self.busy = True, False
                    self.active_key, info = value
                    self.next_check = time.monotonic() + 60
                    self.stop_button.config(state='normal')
                    self.status.set('代理已连通。请保持本工具运行，并手动重启 Codex。')
                    messagebox.showinfo('代理已启用', '汉化成功，请重启Codex生效\n\n代理连接测试已通过；实际中文界面请重启后确认。\n请保持本工具运行。')
                elif kind == 'checked':
                    self.checking = False
                    self.next_check = time.monotonic() + 60
                    if value:
                        if self.active:
                            self.stop()
                            messagebox.showerror('代理已停止', value)
                            continue
                else:
                    self.busy = False
                    self.start_button.config(state='normal')
                    self.status.set('启用失败，未保持代理。')
                    messagebox.showerror('启用失败', value)
        except queue.Empty:
            pass
        if self.active and self.proxy.process.poll() is not None:
            self.stop()
            messagebox.showerror('代理中断', '代理组件已退出，已恢复原代理设置。')
        if self.active and not self.checking and time.monotonic() >= self.next_check:
            self.checking = True
            key = self.active_key
            def check():
                try:
                    error = '' if verify_key(key) else '密钥已失效，请联系管理员。'
                except Exception:
                    error = '无法续验密钥，请检查网络后重新启用。'
                self.events.put(('checked', error))

            threading.Thread(target=check, daemon=True).start()
        self.root.after(200, self.poll)

    def stop(self):
        self.proxy.stop()
        self.active = False
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.status.set('代理已停止，原设置已恢复。')

    def close(self):
        if self.busy:
            messagebox.showinfo('请稍候', '正在测试代理，请等待完成后关闭。')
            return
        self.stop()
        self.root.destroy()


if __name__ == '__main__':
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    mutex = kernel.CreateMutexW(None, False, 'Local\\CodexChineseProxy')
    already_running = ctypes.get_last_error() == 183
    root = tk.Tk()
    if already_running:
        root.withdraw()
        messagebox.showinfo('工具已运行', '请使用已经打开的代理工具。')
        root.destroy()
    else:
        try:
            App(root)
            root.mainloop()
        except Exception as error:
            messagebox.showerror('工具启动失败', str(error))
