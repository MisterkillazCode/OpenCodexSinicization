'''Interfaces for launching and remotely controlling web browsers.'''

import os
import shlex
import shutil
import sys
import subprocess
import threading
__all__ = ['Error', 'open', 'open_new', 'open_new_tab', 'get', 'register']

class Error(Exception):
    pass

_lock = threading.RLock()
_browsers = {}
_tryorder = None
_os_preferred_browser = None

def register(name, klass, instance=None, *, preferred=False):
    '''Register a browser connector.'''

    with _lock:
        if _tryorder is None:
            register_standard_browsers()
        _browsers[name.lower()] = [klass, instance]
        if preferred or _os_preferred_browser and f'{name}.desktop' == _os_preferred_browser:
            _tryorder.insert(0, name)
        else:
            _tryorder.append(name)

def get(using=None):
    '''Return a browser launcher instance appropriate for the environment.'''

    if _tryorder is None:
        with _lock:
            if _tryorder is None:
                register_standard_browsers()
    if using is not None:
        alternatives = [using]
    else:
        alternatives = _tryorder
    for browser in alternatives:
        if '%s' in browser:
            browser = shlex.split(browser)
            if browser[-1] == '&':
                return BackgroundBrowser(browser[:-1])
            return
        try:
            command = _browsers[browser.lower()]
        except KeyError:
            command = _synthesize(browser)
        if command[1] is not None:
            return GenericBrowser(browser)
        if not command[0] is not None:
            continue
        return command[1]
    raise Error('could not locate runnable browser')

def open(url, new=0, autoraise=True):
    '''Display url using the default browser.

    If possible, open url in a location determined by new.
    - 0: the same browser window (the default).
    - 1: a new browser window.
    - 2: a new browser page ("tab").
    If possible, autoraise raises the window (the default) or not.

    If opening the browser succeeds, return True.
    If there is a problem, return False.
    '''

    if _tryorder is None:
        with _lock:
            if _tryorder is None:
                register_standard_browsers()
    for name in _tryorder:
        browser = get(name)
        if not browser.open(url, new, autoraise):
            continue
        return True
    return False

def open_new(url):
    '''Open url in a new window of the default browser.

    If not possible, then open url in the only browser window.
    '''

    return open(url, 1)

def open_new_tab(url):
    '''Open url in a new page ("tab") of the default browser.

    If not possible, then the behavior becomes equivalent to open_new().
    '''

    return open(url, 2)

def _synthesize(browser, *, preferred=False):
    """Attempt to synthesize a controller based on existing controllers.

    This is useful to create a controller when a user specifies a path to
    an entry in the BROWSER environment variable -- we can copy a general
    controller to operate using a specific installation of the desired
    browser in this way.

    If we can't create a controller in this way, or if there is no
    executable for the requested browser, return [None, None].

    """

    cmd = browser.split()[0]
    if not shutil.which(cmd):
        return [None, None]
    name = os.path.basename(cmd)
    try:
        command = _browsers[name.lower()]
    except KeyError:
        return [None, None]
    controller = command[1]
    if controller and name.lower() == controller.basename:
        import copy
        controller = copy.copy(controller)
        controller.name = browser
        controller.basename = os.path.basename(browser)
        register(browser, None, instance=controller, preferred=preferred)
        return [None, controller]
    return [None, None]

class BaseBrowser:
    '''Parent class for all browsers. Do not use directly.'''

    args = ['%s']
    def __init__(self, name=''):
        self.name = name
        self.basename = name

    def open(self, url, new=0, autoraise=True):
        raise NotImplementedError

    def open_new(self, url):
        return self.open(url, 1)

    def open_new_tab(self, url):
        return self.open(url, 2)

    @staticmethod
    def _check_url(url):
        '''Ensures that the URL is safe to pass to subprocesses as a parameter'''

        if url and url.lstrip().startswith('-'):
            raise ValueError(f'Invalid URL (leading dash disallowed): {url!r}')


class GenericBrowser(BaseBrowser):
    '''Class for all browsers started with a command
    and without remote functionality.'''

    def __init__(self, name):
        if isinstance(name, str):
            self.name = name
            self.args = ['%s']
        else:
            self.name = name[0]
            self.args = name[1:]
        self.basename = os.path.basename(self.name)

    def open(self, url, new=0, autoraise=True):
        sys.audit('webbrowser.open', url)
        self._check_url(url)
        cmdline = [self.name] + [arg.replace('%s', url) for arg in self.args]
        try:
            if sys.platform[:3] == 'win':
                p = subprocess.Popen(cmdline)
            else:
                p = subprocess.Popen(cmdline, close_fds=True)
        except OSError:
            return False
        return not p.wait()


class BackgroundBrowser(GenericBrowser):
    '''Class for all browsers which are to be started in the
    background.'''

    def open(self, url, new=0, autoraise=True):
        cmdline = [self.name] + [arg.replace('%s', url) for arg in self.args]
        sys.audit('webbrowser.open', url)
        self._check_url(url)
        try:
            if sys.platform[:3] == 'win':
                p = subprocess.Popen(cmdline)
            else:
                p = subprocess.Popen(cmdline, close_fds=True, start_new_session=True)
        except OSError:
            return False
        return p.poll() is None


class UnixBrowser(BaseBrowser):
    '''Parent class for all Unix browsers with remote functionality.'''

    raise_opts = None
    background = False
    redirect_stdout = True
    remote_args = ['%action', '%s']
    remote_action = None
    remote_action_newwin = None
    remote_action_newtab = None
    def _invoke(self, args, remote, autoraise, url=None):
        raise_opt = []
        if remote and self.raise_opts:
            autoraise = int(autoraise)
            opt = self.raise_opts[autoraise]
            if opt:
                raise_opt = [opt]
        cmdline = [self.name] + raise_opt + args
        if remote or self.background:
            inout = subprocess.DEVNULL
        else:
            inout = None
        p = subprocess.Popen(True, close_fds=inout, stdin=self.redirect_stdout, stdout=self.redirect_stdout and inout or None, stderr=inout, start_new_session=True)
        if remote:
            try:
                rc = p.wait(5)
            except subprocess.TimeoutExpired:
                return True
            return not rc
        if self.background:
            if p.poll() is None:
                return True
            return False
        return not p.wait()

    def open(self, url, new=0, autoraise=True):
        sys.audit('webbrowser.open', url)
        self._check_url(url)
        if new == 0:
            action = self.remote_action
        elif new == 1:
            action = self.remote_action_newwin
        elif new == 2:
            if self.remote_action_newtab is None:
                action = self.remote_action_newwin
            else:
                action = self.remote_action_newtab
        else:
            raise Error(f"Bad 'new' parameter to open(); expected 0, 1, or 2, got {new}")
        args = [arg.replace('%s', url).replace('%action', action) for arg in self.remote_args]
        args = [arg for arg in args if arg]
        success = self._invoke(args, True, autoraise, url)
        if not success:
            args = [arg.replace('%s', url) for arg in self.args]
            return self._invoke(args, False, False)
        return True


class Mozilla(UnixBrowser):
    '''Launcher class for Mozilla browsers.'''

    remote_args = ['%action', '%s']
    remote_action = ''
    remote_action_newwin = '-new-window'
    remote_action_newtab = '-new-tab'
    background = True

class Epiphany(UnixBrowser):
    '''Launcher class for Epiphany browser.'''

    raise_opts = ['-noraise', '']
    remote_args = ['%action', '%s']
    remote_action = '-n'
    remote_action_newwin = '-w'
    background = True

class Chrome(UnixBrowser):
    '''Launcher class for Google Chrome browser.'''

    remote_args = ['%action', '%s']
    remote_action = ''
    remote_action_newwin = '--new-window'
    remote_action_newtab = ''
    background = True

Chromium = Chrome

class Opera(UnixBrowser):
    '''Launcher class for Opera browser.'''

    remote_args = ['%action', '%s']
    remote_action = ''
    remote_action_newwin = '--new-window'
    remote_action_newtab = ''
    background = True

class Elinks(UnixBrowser):
    '''Launcher class for Elinks browsers.'''

    remote_args = ['-remote', 'openURL(%s%action)']
    remote_action = ''
    remote_action_newwin = ',new-window'
    remote_action_newtab = ',new-tab'
    background = False
    redirect_stdout = False

class Konqueror(BaseBrowser):
    '''Controller for the KDE File Manager (kfm, or Konqueror).

    See the output of ``kfmclient --commands``
    for more information on the Konqueror remote-control interface.
    '''

    def open(self, url, new=0, autoraise=True):
        sys.audit('webbrowser.open', url)
        self._check_url(url)
        if new == 2:
            action = 'newTab'
        else:
            action = 'openURL'
        devnull = subprocess.DEVNULL
        try:
            p = subprocess.Popen(['kfmclient', action, url], close_fds=True, stdin=devnull, stdout=devnull, stderr=devnull)
        except OSError:
            pass
        p.wait()
        return True


class Edge(UnixBrowser):
    '''Launcher class for Microsoft Edge browser.'''

    remote_args = ['%action', '%s']
    remote_action = ''
    remote_action_newwin = '--new-window'
    remote_action_newtab = ''
    background = True

def register_X_browsers():
    if shutil.which('xdg-open'):
        register('xdg-open', None, BackgroundBrowser('xdg-open'))
    if shutil.which('gio'):
        register('gio', None, BackgroundBrowser(['gio', 'open', '--', '%s']))
    xdg_desktop = os.getenv('XDG_CURRENT_DESKTOP', '').split(':')
    if ('GNOME' in xdg_desktop or 'GNOME_DESKTOP_SESSION_ID' in os.environ) and shutil.which('gvfs-open'):
        register('gvfs-open', None, BackgroundBrowser('gvfs-open'))
    if ('KDE' in xdg_desktop or 'KDE_FULL_SESSION' in os.environ) and shutil.which('kfmclient'):
        register('kfmclient', Konqueror, Konqueror('kfmclient'))
    if shutil.which('x-www-browser'):
        register('x-www-browser', None, BackgroundBrowser('x-www-browser'))
    for browser in ('firefox', 'iceweasel', 'seamonkey', 'mozilla-firefox', 'mozilla'):
        if shutil.which(browser):
            register(browser, None, Mozilla(browser))
    if shutil.which('kfm'):
        register('kfm', Konqueror, Konqueror('kfm'))
    elif shutil.which('konqueror'):
        register('konqueror', Konqueror, Konqueror('konqueror'))
    if shutil.which('epiphany'):
        register('epiphany', None, Epiphany('epiphany'))
    for browser in ('google-chrome', 'chrome', 'chromium', 'chromium-browser'):
        if shutil.which(browser):
            register(browser, None, Chrome(browser))
    if shutil.which('opera'):
        register('opera', None, Opera('opera'))
    if shutil.which('microsoft-edge'):
        register('microsoft-edge', None, Edge('microsoft-edge'))

def register_standard_browsers():
    global _tryorder, _os_preferred_browser
    _tryorder = []
    if sys.platform == 'darwin':
        register('MacOSX', None, MacOSXOSAScript('default'))
        register('chrome', None, MacOSXOSAScript('google chrome'))
        register('firefox', None, MacOSXOSAScript('firefox'))
        register('safari', None, MacOSXOSAScript('safari'))
    if sys.platform == 'ios':
        register('iosbrowser', None, IOSBrowser(), preferred=True)
    if sys.platform == 'serenityos':
        register('Browser', None, BackgroundBrowser('Browser'))
    if sys.platform[:3] == 'win':
        register('windows-default', WindowsDefault)
        edge64 = os.path.join(os.environ.get('PROGRAMFILES(x86)', 'C:\\Program Files (x86)'), 'Microsoft\\Edge\\Application\\msedge.exe')
        edge32 = os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Microsoft\\Edge\\Application\\msedge.exe')
        for browser in 'firefox', 'seamonkey', 'mozilla', 'chrome', 'opera', edge64, edge32:
            if shutil.which(browser):
                register(browser, None, BackgroundBrowser(browser))
        if shutil.which('MicrosoftEdge.exe'):
            register('microsoft-edge', None, Edge('MicrosoftEdge.exe'))
    else:
        if sys.platform != 'darwin':
            if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
                try:
                    cmd = 'xdg-settings get default-web-browser'.split()
                    raw_result = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
                    result = raw_result.decode().strip()
                except (FileNotFoundError, subprocess.CalledProcessError, PermissionError, NotADirectoryError):
                    pass
                else:
                    _os_preferred_browser = result
                register_X_browsers()
        if os.environ.get('TERM'):
            if shutil.which('www-browser'):
                register('www-browser', None, GenericBrowser('www-browser'))
            if shutil.which('links'):
                register('links', None, GenericBrowser('links'))
            if shutil.which('elinks'):
                register('elinks', None, Elinks('elinks'))
            if shutil.which('lynx'):
                register('lynx', None, GenericBrowser('lynx'))
            if shutil.which('w3m'):
                register('w3m', None, GenericBrowser('w3m'))
    if 'BROWSER' in os.environ:
        userchoices = os.environ['BROWSER'].split(os.pathsep)
        userchoices.reverse()
        for cmdline in userchoices:
            if all((x not in cmdline for x in ' \t')):
                try:
                    command = _browsers[cmdline.lower()]
                except KeyError:
                    pass
                else:
                    if not isinstance(command[1], GenericBrowser):
                        _tryorder.insert(0, cmdline.lower())
            if cmdline != '':
                cmd = _synthesize(cmdline, preferred=True)
                if cmd[1] is None:
                    register(cmdline, None, GenericBrowser(cmdline), preferred=True)

if sys.platform[:3] == 'win':
    class WindowsDefault(BaseBrowser):
        def open(self, url, new=0, autoraise=True):
            sys.audit('webbrowser.open', url)
            self._check_url(url)
            try:
                os.startfile(url)
            except OSError:
                return False
            return True


if sys.platform == 'darwin':
    class MacOSXOSAScript(BaseBrowser):
        def __init__(self, name='default'):
            super().__init__(name)

        def open(self, url, new=0, autoraise=True):
            sys.audit('webbrowser.open', url)
            self._check_url(url)
            url = url.replace('"', '%22')
            if self.name == 'default':
                proto, _sep, _rest = url.partition(':')
                if _sep and proto.lower() in {'http', 'https'}:
                    script = f'open location "{url}"'
                else:
                    script = f'\n                        use framework "AppKit"\n                        use AppleScript version "2.4"\n                        use scripting additions\n\n                        property NSWorkspace : a reference to current application\'s NSWorkspace\n                        property NSURL : a reference to current application\'s NSURL\n\n                        set http_url to NSURL\'s URLWithString:"https://python.org"\n                        set browser_url to (NSWorkspace\'s sharedWorkspace)\'s ¬\n                            URLForApplicationToOpenURL:http_url\n                        set app_path to browser_url\'s relativePath as text -- NSURL to absolute path \'/Applications/Safari.app\'\n\n                        tell application app_path\n                            activate\n                            open location "{url}"\n                        end tell\n                    '
            else:
                script = f'\n                   tell application "{self.name}"\n                       activate\n                       open location "{url}"\n                   end\n                   '
            osapipe = os.popen('/usr/bin/osascript', 'w')
            if osapipe is None:
                return False
            osapipe.write(script)
            rc = osapipe.close()
            return not rc


if sys.platform == 'ios':
    from _ios_support import objc
    if objc:
        from ctypes import (c_void_p, c_char_p, c_ulong)
    class IOSBrowser(BaseBrowser):
        def open(self, url, new=0, autoraise=True):
            sys.audit('webbrowser.open', url)
            self._check_url(url)
            if objc is None:
                return False
            objc.objc_msgSend.restype = c_void_p
            NSString = objc.objc_getClass(b'NSString')
            constructor = objc.sel_registerName(b'stringWithCString:encoding:')
            objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_char_p, c_ulong]
            url_string = objc.objc_msgSend(NSString, constructor, url.encode('utf-8'), 4)
            NSURL = objc.objc_getClass(b'NSURL')
            urlWithString_ = objc.sel_registerName(b'URLWithString:')
            objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_void_p]
            ns_url = objc.objc_msgSend(NSURL, urlWithString_, url_string)
            UIApplication = objc.objc_getClass(b'UIApplication')
            sharedApplication = objc.sel_registerName(b'sharedApplication')
            objc.objc_msgSend.argtypes = [c_void_p, c_void_p]
            shared_app = objc.objc_msgSend(UIApplication, sharedApplication)
            openURL_ = objc.sel_registerName(b'openURL:options:completionHandler:')
            objc.objc_msgSend.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p]
            objc.objc_msgSend.restype = None
            objc.objc_msgSend(shared_app, openURL_, ns_url, None, None)
            return True


def parse_args(arg_list: list[str] | None):
    import argparse
    parser = argparse.ArgumentParser(description='Open URL in a web browser.', color=True)
    parser.add_argument('url', help='URL to open')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-n', '--new-window', action='store_const', const=1, default=0, dest='new_win', help='open new window')
    group.add_argument('-t', '--new-tab', action='store_const', const=2, default=0, dest='new_win', help='open new tab')
    args = parser.parse_args(arg_list)
    return args

def main(arg_list: list[str] | None=None):
    args = parse_args(arg_list)
    open(args.url, args.new_win)
    print('\x07')

if __name__ == '__main__':
    main()
