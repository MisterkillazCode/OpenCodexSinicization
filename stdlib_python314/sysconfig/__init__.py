"""Access to Python's configuration information."""

import os
import sys
import threading
from os.path import realpath
__all__ = ['get_config_h_filename', 'get_config_var', 'get_config_vars', 'get_makefile_filename', 'get_path', 'get_path_names', 'get_paths', 'get_platform', 'get_python_version', 'get_scheme_names', 'parse_config_h']
_ALWAYS_STR = {'IPHONEOS_DEPLOYMENT_TARGET', 'MACOSX_DEPLOYMENT_TARGET'}
_INSTALL_SCHEMES = {'posix_prefix': {'stdlib': '{installed_base}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'platstdlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'purelib': '{base}/lib/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'platlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'include': '{installed_base}/include/{implementation_lower}{py_version_short}{abiflags}', 'platinclude': '{installed_platbase}/include/{implementation_lower}{py_version_short}{abiflags}', 'scripts': '{base}/bin', 'data': '{base}'}, 'posix_home': {'stdlib': '{installed_base}/lib/{implementation_lower}', 'platstdlib': '{base}/lib/{implementation_lower}', 'purelib': '{base}/lib/{implementation_lower}', 'platlib': '{base}/lib/{implementation_lower}', 'include': '{installed_base}/include/{implementation_lower}', 'platinclude': '{installed_base}/include/{implementation_lower}', 'scripts': '{base}/bin', 'data': '{base}'}, 'nt': {'stdlib': '{installed_base}/Lib', 'platstdlib': '{base}/Lib', 'purelib': '{base}/Lib/site-packages', 'platlib': '{base}/Lib/site-packages', 'include': '{installed_base}/Include', 'platinclude': '{installed_base}/Include', 'scripts': '{base}/Scripts', 'data': '{base}'}, 'posix_venv': {'stdlib': '{installed_base}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'platstdlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'purelib': '{base}/lib/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'platlib': '{platbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'include': '{installed_base}/include/{implementation_lower}{py_version_short}{abiflags}', 'platinclude': '{installed_platbase}/include/{implementation_lower}{py_version_short}{abiflags}', 'scripts': '{base}/bin', 'data': '{base}'}, 'nt_venv': {'stdlib': '{installed_base}/Lib', 'platstdlib': '{base}/Lib', 'purelib': '{base}/Lib/site-packages', 'platlib': '{base}/Lib/site-packages', 'include': '{installed_base}/Include', 'platinclude': '{installed_base}/Include', 'scripts': '{base}/Scripts', 'data': '{base}'}}
if os.name == 'nt':
    _INSTALL_SCHEMES['venv'] = _INSTALL_SCHEMES['nt_venv']
else:
    _INSTALL_SCHEMES['venv'] = _INSTALL_SCHEMES['posix_venv']

def _get_implementation():
    return 'Python'

def _getuserbase():
    env_base = os.environ.get('PYTHONUSERBASE', None)
    if env_base:
        return env_base
    system_name = os.environ.get('_PYTHON_HOST_PLATFORM', sys.platform).split('-')[0]
    if system_name in {'ios', 'tvos', 'wasi', 'vxworks', 'watchos', 'emscripten'}:
        return
    def joinuser(*args):
        return os.path.expanduser(os.path.join(*args))

    if os.name == 'nt':
        base = os.environ.get('APPDATA') or '~'
        return joinuser(base, _get_implementation())
    if sys.platform == 'darwin' and sys._framework:
        return joinuser('~', 'Library', sys._framework, f'{sys.version_info[0]}.{sys.version_info[1]}')
    return joinuser('~', '.local')

_HAS_USER_BASE = _getuserbase() is not None
if _HAS_USER_BASE:
    _INSTALL_SCHEMES |= {'nt_user': {'stdlib': '{userbase}/{implementation}{py_version_nodot_plat}', 'platstdlib': '{userbase}/{implementation}{py_version_nodot_plat}', 'purelib': '{userbase}/{implementation}{py_version_nodot_plat}/site-packages', 'platlib': '{userbase}/{implementation}{py_version_nodot_plat}/site-packages', 'include': '{userbase}/{implementation}{py_version_nodot_plat}/Include', 'scripts': '{userbase}/{implementation}{py_version_nodot_plat}/Scripts', 'data': '{userbase}'}, 'posix_user': {'stdlib': '{userbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'platstdlib': '{userbase}/{platlibdir}/{implementation_lower}{py_version_short}{abi_thread}', 'purelib': '{userbase}/lib/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'platlib': '{userbase}/lib/{implementation_lower}{py_version_short}{abi_thread}/site-packages', 'include': '{userbase}/include/{implementation_lower}{py_version_short}{abi_thread}', 'scripts': '{userbase}/bin', 'data': '{userbase}'}, 'osx_framework_user': {'stdlib': '{userbase}/lib/{implementation_lower}', 'platstdlib': '{userbase}/lib/{implementation_lower}', 'purelib': '{userbase}/lib/{implementation_lower}/site-packages', 'platlib': '{userbase}/lib/{implementation_lower}/site-packages', 'include': '{userbase}/include/{implementation_lower}{py_version_short}', 'scripts': '{userbase}/bin', 'data': '{userbase}'}}
_SCHEME_KEYS = ('stdlib', 'platstdlib', 'purelib', 'platlib', 'include', 'scripts', 'data')
_PY_VERSION = sys.version.split()[0]
_PY_VERSION_SHORT = f'{sys.version_info[0]}.{sys.version_info[1]}'
_PY_VERSION_SHORT_NO_DOT = f'{sys.version_info[0]}{sys.version_info[1]}'
_BASE_PREFIX = os.path.normpath(sys.base_prefix)
_BASE_EXEC_PREFIX = os.path.normpath(sys.base_exec_prefix)
_CONFIG_VARS_LOCK = threading.RLock()
_CONFIG_VARS = None
_CONFIG_VARS_INITIALIZED = False
_USER_BASE = None

def _safe_realpath(path):
    try:
        return realpath(path)
    except OSError:
        return path

if sys.executable:
    _PROJECT_BASE = os.path.dirname(_safe_realpath(sys.executable))
else:
    _PROJECT_BASE = _safe_realpath(os.getcwd())
_sys_home = getattr(sys, '_home', None)
if _sys_home:
    _PROJECT_BASE = _sys_home
if os.name == 'nt' and _safe_realpath(_PROJECT_BASE).startswith(_safe_realpath(f'{_BASE_PREFIX}\\PCbuild')):
    _PROJECT_BASE = _BASE_PREFIX
if '_PYTHON_PROJECT_BASE' in os.environ:
    _PROJECT_BASE = _safe_realpath(os.environ['_PYTHON_PROJECT_BASE'])

def is_python_build(check_home=None):
    if check_home is not None:
        import warnings
        warnings.warn('The check_home argument of sysconfig.is_python_build is deprecated and its value is ignored. It will be removed in Python 3.15.', DeprecationWarning, stacklevel=2)
    for fn in ('Setup', 'Setup.local'):
        if not os.path.isfile(os.path.join(_PROJECT_BASE, 'Modules', fn)):
            continue
        return True
    return False

_PYTHON_BUILD = is_python_build()
if _PYTHON_BUILD:
    for scheme in ('posix_prefix', 'posix_home'):
        scheme = _INSTALL_SCHEMES[scheme]
        scheme['headers'] = scheme['include']
        scheme['include'] = '{srcdir}/Include'
        scheme['platinclude'] = '{projectbase}/.'
    del scheme

def _subst_vars(s, local_vars):
    try:
        return s.format(**local_vars)
    except KeyError as var:
        try:
            pass
        except KeyError:
            raise AttributeError(f'{var}') from None
        return s.format(**os.environ)

def _extend_dict(target_dict, other_dict):
    target_keys = target_dict.keys()
    for key, value in other_dict.items():
        if key in target_keys:
            continue
        target_dict[key] = value

def _expand_vars(scheme, vars):
    res = {}
    if vars is None:
        vars = {}
    _extend_dict(vars, get_config_vars())
    if os.name == 'nt':
        vars = vars | {'platlibdir': 'lib'}
    for key, value in _INSTALL_SCHEMES[scheme].items():
        if os.name in ('posix', 'nt'):
            value = os.path.expanduser(value)
        res[key] = os.path.normpath(_subst_vars(value, vars))
    return res

def _get_preferred_schemes():
    if os.name == 'nt':
        return {'prefix': 'nt', 'home': 'posix_home', 'user': 'nt_user'}
    if sys.platform == 'darwin' and sys._framework:
        return {'prefix': 'posix_prefix', 'home': 'posix_home', 'user': 'osx_framework_user'}
    return {'prefix': 'posix_prefix', 'home': 'posix_home', 'user': 'posix_user'}

def get_preferred_scheme(key):
    if key == 'prefix' and sys.prefix != sys.base_prefix:
        return 'venv'
    scheme = _get_preferred_schemes()[key]
    if scheme not in _INSTALL_SCHEMES:
        raise ValueError(f'{key!r} returned {scheme!r}, which is not a valid scheme on this platform')
    return scheme

def get_default_scheme():
    return get_preferred_scheme('prefix')

def get_makefile_filename():
    '''Return the path of the Makefile.'''

    if (cross_base := os.environ.get('_PYTHON_PROJECT_BASE')):
        return os.path.join(cross_base, 'Makefile')
    if _PYTHON_BUILD:
        return os.path.join(_PROJECT_BASE, 'Makefile')
    if hasattr(sys, 'abiflags'):
        config_dir_name = f'config-{_PY_VERSION_SHORT}{sys.abiflags}'
    else:
        config_dir_name = 'config'
    if hasattr(sys.implementation, '_multiarch'):
        config_dir_name += f'-{sys.implementation._multiarch}'
    return os.path.join(get_path('stdlib'), config_dir_name, 'Makefile')

def _import_from_directory(path, name):
    if name not in sys.modules:
        import importlib.machinery
        import importlib.util
        spec = importlib.machinery.PathFinder.find_spec(name, [path])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]

def _get_sysconfigdata_name():
    multiarch = getattr(sys.implementation, '_multiarch', '')
    return os.environ.get('_PYTHON_SYSCONFIGDATA_NAME', f'_sysconfigdata_{sys.abiflags}_{sys.platform}_{multiarch}')

def _get_sysconfigdata():
    import importlib
    name = _get_sysconfigdata_name()
    path = os.environ.get('_PYTHON_SYSCONFIGDATA_PATH')
    if path:
        module = _import_from_directory(path, name)
        return module.build_time_vars
    module = importlib.import_module(name)
    return module.build_time_vars

def _installation_is_relocated():
    '''Is the Python installation running from a different prefix than what was targetted when building?'''

    if os.name != 'posix':
        raise NotImplementedError('sysconfig._installation_is_relocated() is currently only supported on POSIX')
    data = _get_sysconfigdata()
    return data['prefix'] != getattr(sys, 'base_prefix', '') or data['exec_prefix'] != getattr(sys, 'base_exec_prefix', '')

def _init_posix(vars):
    '''Initialize the module as appropriate for POSIX systems.'''

    vars.update(_get_sysconfigdata() | vars)

def _init_non_posix(vars):
    '''Initialize the module as appropriate for NT'''

    import _winapi
    import _sysconfig
    vars['LIBDEST'] = get_path('stdlib')
    vars['BINLIBDEST'] = get_path('platstdlib')
    vars['INCLUDEPY'] = get_path('include')
    vars.update(_sysconfig.config_vars())
    vars['ABIFLAGS'] = ''.join(('t' if vars['Py_GIL_DISABLED'] else '', '_d' if vars['Py_DEBUG'] else ''))
    vars['LIBDIR'] = _safe_realpath(os.path.join(get_config_var('installed_base'), 'libs'))
    if hasattr(sys, 'dllhandle'):
        dllhandle = _winapi.GetModuleFileName(sys.dllhandle)
        vars['LIBRARY'] = os.path.basename(_safe_realpath(dllhandle))
        vars['LDLIBRARY'] = vars['LIBRARY']
    vars['EXE'] = '.exe'
    vars['VERSION'] = _PY_VERSION_SHORT_NO_DOT
    vars['BINDIR'] = os.path.dirname(_safe_realpath(sys.executable))
    vars['TZPATH'] = ''

def parse_config_h(fp, vars=None):
    '''Parse a config.h-style file.

    A dictionary containing name/value pairs is returned.  If an
    optional dictionary is passed in as the second argument, it is
    used instead of a new dictionary.
    '''

    if vars is None:
        vars = {}
    import re
    define_rx = re.compile('#define ([A-Z][A-Za-z0-9_]+) (.*)\n')
    undef_rx = re.compile('/[*] #undef ([A-Z][A-Za-z0-9_]+) [*]/\n')
    while True:
        line = fp.readline()
        if not line:
            return vars
        m = define_rx.match(line)
        if m:
            n, v = m.group(1, 2)
            try:
                if n in _ALWAYS_STR:
                    raise ValueError
                v = int(v)
            except ValueError:
                pass
            vars[n] = v
        else:
            m = undef_rx.match(line)
            if m:
                vars[m.group(1)] = 0

def get_config_h_filename():
    '''Return the path of pyconfig.h.'''

    if _PYTHON_BUILD:
        if os.name == 'nt':
            inc_dir = os.path.join(_PROJECT_BASE, 'PC')
        else:
            inc_dir = _PROJECT_BASE
    else:
        inc_dir = get_path('platinclude')
    return os.path.join(inc_dir, 'pyconfig.h')

def get_scheme_names():
    '''Return a tuple containing the schemes names.'''

    return tuple(sorted(_INSTALL_SCHEMES))

def get_path_names():
    '''Return a tuple containing the paths names.'''

    return _SCHEME_KEYS

def get_paths(scheme=get_default_scheme(), vars=None, expand=True):
    '''Return a mapping containing an install scheme.

    ``scheme`` is the install scheme name. If not provided, it will
    return the default scheme for the current platform.
    '''

    if expand:
        return _expand_vars(scheme, vars)
    return _INSTALL_SCHEMES[scheme]

def get_path(name, scheme=get_default_scheme(), vars=None, expand=True):
    '''Return a path corresponding to the scheme.

    ``scheme`` is the install scheme name.
    '''

    return get_paths(scheme, vars, expand)[name]

def _init_config_vars():
    global _CONFIG_VARS, _CONFIG_VARS_INITIALIZED
    _CONFIG_VARS = {}
    prefix = os.path.normpath(sys.prefix)
    exec_prefix = os.path.normpath(sys.exec_prefix)
    base_prefix = _BASE_PREFIX
    base_exec_prefix = _BASE_EXEC_PREFIX
    try:
        abiflags = sys.abiflags
    except AttributeError:
        abiflags = ''
    if os.name == 'posix':
        _init_posix(_CONFIG_VARS)
        if '_PYTHON_PROJECT_BASE' in os.environ:
            prefix = _CONFIG_VARS['host_prefix']
            exec_prefix = _CONFIG_VARS['host_exec_prefix']
            base_prefix = _CONFIG_VARS['host_prefix']
            base_exec_prefix = _CONFIG_VARS['host_exec_prefix']
            abiflags = _CONFIG_VARS['ABIFLAGS']
    _CONFIG_VARS['prefix'] = prefix
    _CONFIG_VARS['exec_prefix'] = exec_prefix
    _CONFIG_VARS['py_version'] = _PY_VERSION
    _CONFIG_VARS['py_version_short'] = _PY_VERSION_SHORT
    _CONFIG_VARS['py_version_nodot'] = _PY_VERSION_SHORT_NO_DOT
    _CONFIG_VARS['installed_base'] = base_prefix
    _CONFIG_VARS['base'] = prefix
    _CONFIG_VARS['installed_platbase'] = base_exec_prefix
    _CONFIG_VARS['platbase'] = exec_prefix
    _CONFIG_VARS['projectbase'] = _PROJECT_BASE
    _CONFIG_VARS['platlibdir'] = sys.platlibdir
    _CONFIG_VARS['implementation'] = _get_implementation()
    _CONFIG_VARS['implementation_lower'] = _get_implementation().lower()
    _CONFIG_VARS['abiflags'] = abiflags
    try:
        _CONFIG_VARS['py_version_nodot_plat'] = sys.winver.replace('.', '')
    except AttributeError:
        _CONFIG_VARS['py_version_nodot_plat'] = ''
    if os.name == 'nt':
        _init_non_posix(_CONFIG_VARS)
        _CONFIG_VARS['VPATH'] = sys._vpath
    if _HAS_USER_BASE:
        _CONFIG_VARS['userbase'] = _getuserbase()
    _CONFIG_VARS['abi_thread'] = 't' if _CONFIG_VARS.get('Py_GIL_DISABLED') else ''
    srcdir = _CONFIG_VARS.get('srcdir', _PROJECT_BASE)
    if os.name == 'posix':
        if _PYTHON_BUILD:
            base = os.path.dirname(get_makefile_filename())
            srcdir = os.path.join(base, srcdir)
        else:
            srcdir = os.path.dirname(get_makefile_filename())
    _CONFIG_VARS['srcdir'] = _safe_realpath(srcdir)
    if sys.platform == 'darwin':
        import _osx_support
        _osx_support.customize_config_vars(_CONFIG_VARS)
    _CONFIG_VARS_INITIALIZED = True

def get_config_vars(*args):
    """With no arguments, return a dictionary of all configuration
    variables relevant for the current platform.

    On Unix, this means every variable defined in Python's installed Makefile;
    On Windows it's a much smaller set.

    With arguments, return a list of values that result from looking up
    each argument in the configuration variable dictionary.
    """

    global _CONFIG_VARS_INITIALIZED
    if _CONFIG_VARS_INITIALIZED:
        prefix = os.path.normpath(sys.prefix)
        exec_prefix = os.path.normpath(sys.exec_prefix)
        if _CONFIG_VARS['prefix'] != prefix or _CONFIG_VARS['exec_prefix'] != exec_prefix:
            with _CONFIG_VARS_LOCK:
                _CONFIG_VARS_INITIALIZED = False
                _init_config_vars()
    else:
        with _CONFIG_VARS_LOCK:
            if _CONFIG_VARS is None:
                _init_config_vars()
    if args:
        vals = []
        for name in args:
            vals.append(_CONFIG_VARS.get(name))
        return vals
    return _CONFIG_VARS

def get_config_var(name):
    """Return the value of a single variable using the dictionary returned by
    'get_config_vars()'.

    Equivalent to get_config_vars().get(name)
    """

    return get_config_vars().get(name)

def get_platform():
    """Return a string that identifies the current platform.

    This is used mainly to distinguish platform-specific build directories and
    platform-specific built distributions.  Typically includes the OS name and
    version and the architecture (as supplied by 'os.uname()'), although the
    exact information included depends on the OS; on Linux, the kernel version
    isn't particularly important.

    Examples of returned values:


    Windows:

    - win-amd64 (64-bit Windows on AMD64, aka x86_64, Intel64, and EM64T)
    - win-arm64 (64-bit Windows on ARM64, aka AArch64)
    - win32 (all others - specifically, sys.platform is returned)

    POSIX based OS:

    - linux-x86_64
    - macosx-15.5-arm64
    - macosx-26.0-universal2 (macOS on Apple Silicon or Intel)
    - android-24-arm64_v8a

    For other non-POSIX platforms, currently just returns :data:`sys.platform`."""

    if os.name == 'nt':
        if 'amd64' in sys.version.lower():
            return 'win-amd64'
        if '(arm)' in sys.version.lower():
            return 'win-arm32'
        if '(arm64)' in sys.version.lower():
            return 'win-arm64'
        return sys.platform
    if os.name != 'posix' or not hasattr(os, 'uname'):
        return sys.platform
    if '_PYTHON_HOST_PLATFORM' in os.environ:
        osname, _, machine = os.environ['_PYTHON_HOST_PLATFORM'].partition('-')
        release = None
    else:
        osname, host, release, version, machine = os.uname()
        osname = osname.lower().replace('/', '')
        machine = machine.replace(' ', '_')
        machine = machine.replace('/', '-')
    if osname == 'android' or sys.platform == 'android':
        osname = 'android'
        release = get_config_var('ANDROID_API_LEVEL')
        machine = {'aarch64': 'arm64_v8a', 'arm': 'armeabi_v7a', 'armv7l': 'armeabi_v7a', 'armv8l': 'armeabi_v7a', 'i686': 'x86', 'x86_64': 'x86_64'}[machine]
    else:
        if osname == 'linux':
            return f'{osname}-{machine}'
        if osname[:5] == 'sunos':
            if release[0] >= '5':
                osname = 'solaris'
                release = f'{int(release[0]) - 3}.{release[2:]}'
                bitness = {2147483647: '32bit', 9223372036854775807: '64bit'}
                machine += f'.{bitness[sys.maxsize]}'
        else:
            if osname[:3] == 'aix':
                from _aix_support import aix_platform
                return aix_platform()
            if osname[:6] == 'cygwin':
                osname = 'cygwin'
                import re
                rel_re = re.compile('[\\d.]+')
                m = rel_re.match(release)
                if m:
                    release = m.group()
            elif osname[:6] == 'darwin':
                if sys.platform == 'ios':
                    release = get_config_vars().get('IPHONEOS_DEPLOYMENT_TARGET', '13.0')
                    osname = sys.platform
                    machine = sys.implementation._multiarch
                else:
                    import _osx_support
                    osname, release, machine = _osx_support.get_platform_osx(get_config_vars(), osname, release, machine)
    return '-'.join(map(str, filter(None, (osname, release, machine))))

def get_python_version():
    return _PY_VERSION_SHORT

def _get_python_version_abi():
    return _PY_VERSION_SHORT + get_config_var('abi_thread')

def expand_makefile_vars(s, vars):
    '''Expand Makefile-style variables -- "${foo}" or "$(foo)" -- in
    'string' according to 'vars' (a dictionary mapping variable names to
    values).  Variables not present in 'vars' are silently expanded to the
    empty string.  The variable values in 'vars' should not contain further
    variable expansions; if 'vars' is the output of 'parse_makefile()',
    you're fine.  Returns a variable-expanded version of 's'.
    '''

    import warnings
    warnings.warn('sysconfig.expand_makefile_vars is deprecated and will be removed in Python 3.16. Use sysconfig.get_paths(vars=...) instead.', DeprecationWarning, stacklevel=2)
    import re
    _findvar1_rx = '\\$\\(([A-Za-z][A-Za-z0-9_]*)\\)'
    _findvar2_rx = '\\${([A-Za-z][A-Za-z0-9_]*)}'
    while True:
        m = re.search(_findvar1_rx, s) or re.search(_findvar2_rx, s)
        if not m:
            break
        beg, end = m.span()
        s = s[0:beg] + vars.get(m.group(1)) + s[end:]
    return s

