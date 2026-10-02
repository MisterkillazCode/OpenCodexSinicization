'''
PEP-302 and PEP-451 importers for frozen applications.
'''

import sys
import os
import io
import _frozen_importlib
import _thread
import pyimod01_archive
if sys.flags.verbose and sys.stderr:
    def trace(msg, *a):
        sys.stderr.write(msg % a)
        sys.stderr.write('\n')

else:
    def trace(msg, *a):
        pass

def _decode_source(source_bytes):
    """
    Decode bytes representing source code and return the string. Universal newline support is used in the decoding.
    Based on CPython's implementation of the same functionality:
    https://github.com/python/cpython/blob/3.9/Lib/importlib/_bootstrap_external.py#L679-L688
    """

    from tokenize import detect_encoding
    source_bytes_readline = io.BytesIO(source_bytes).readline
    encoding = detect_encoding(source_bytes_readline)
    newline_decoder = io.IncrementalNewlineDecoder(decoder=None, translate=True)
    return newline_decoder.decode(source_bytes.decode(encoding[0]))

pyz_archive = None
_pyz_tree_lock = _thread.RLock()
_pyz_tree = None

def get_pyz_toc_tree():
    global _pyz_tree
    with _pyz_tree_lock:
        if _pyz_tree is None:
            _pyz_tree = _build_pyz_prefix_tree(pyz_archive)
        return _pyz_tree

_TOP_LEVEL_DIRECTORY_PATHS = []
_TOP_LEVEL_DIRECTORY = os.path.normpath(sys._MEIPASS)
_TOP_LEVEL_DIRECTORY_PATHS.append(_TOP_LEVEL_DIRECTORY)
_RESOLVED_TOP_LEVEL_DIRECTORY = os.path.realpath(_TOP_LEVEL_DIRECTORY)
if os.path.normcase(_RESOLVED_TOP_LEVEL_DIRECTORY) != os.path.normcase(_TOP_LEVEL_DIRECTORY):
    _TOP_LEVEL_DIRECTORY_PATHS.append(_RESOLVED_TOP_LEVEL_DIRECTORY)
_is_macos_app_bundle = False
if sys.platform == 'darwin' and _TOP_LEVEL_DIRECTORY.endswith('Contents/Frameworks'):
    _is_macos_app_bundle = True
    _ALTERNATIVE_TOP_LEVEL_DIRECTORY = os.path.join(os.path.dirname(_TOP_LEVEL_DIRECTORY), 'Resources')
    _TOP_LEVEL_DIRECTORY_PATHS.append(_ALTERNATIVE_TOP_LEVEL_DIRECTORY)
    _RESOLVED_ALTERNATIVE_TOP_LEVEL_DIRECTORY = os.path.join(os.path.dirname(_RESOLVED_TOP_LEVEL_DIRECTORY), 'Resources')
    if _RESOLVED_ALTERNATIVE_TOP_LEVEL_DIRECTORY != _ALTERNATIVE_TOP_LEVEL_DIRECTORY:
        _TOP_LEVEL_DIRECTORY_PATHS.append(_RESOLVED_ALTERNATIVE_TOP_LEVEL_DIRECTORY)

def _build_pyz_prefix_tree(pyz_archive):
    tree = dict()
    for entry_name, entry_data in pyz_archive.toc.items():
        name_components = entry_name.split('.')
        typecode = entry_data[0]
        current = tree
        if typecode in {pyimod01_archive.PYZ_ITEM_PKG, pyimod01_archive.PYZ_ITEM_NSPKG}:
            for name_component in name_components:
                current = current.setdefault(name_component, {})
        else:
            for name_component in name_components[:-1]:
                current = current.setdefault(name_component, {})
            current[name_components[-1]] = ''
    return tree

class PyiFrozenFinder:
    '''
    PyInstaller's frozen path entry finder for specific search path.

    Per-path instances allow us to properly translate the given module name ("fullname") into full PYZ entry name.
    For example, with search path being `sys._MEIPASS`, the module "mypackage.mod" would translate to "mypackage.mod"
    in the PYZ archive. However, if search path was `sys._MEIPASS/myotherpackage/_vendored` (for example, if
    `myotherpacakge` added this path to `sys.path`), then "mypackage.mod" would need to translate to
    "myotherpackage._vendored.mypackage.mod" in the PYZ archive.
    '''

    def __repr__(self):
        return f'{self.__class__.__name__}({self._path})'

    @classmethod
    def path_hook(cls, path):
        trace(f'PyInstaller: running path finder hook for path: {path!r}')
        try:
            finder = cls(path)
            trace('PyInstaller: hook succeeded')
            return finder
        except Exception as e:
            trace(f'PyInstaller: hook failed: {e}')
            raise

    def __init__(self, path):
        self._path = path
        self._pyz_archive = pyz_archive
        for top_level_path in _TOP_LEVEL_DIRECTORY_PATHS:
            try:
                relative_path = os.path.relpath(path, top_level_path)
            except ValueError:
                continue
            if relative_path.startswith('..'):
                continue
            break
        else:
            raise ImportError('Failed to determine relative path w.r.t. top-level application directory.')
        if os.path.isfile(path):
            raise ImportError('only directories are supported')
        if relative_path == '.':
            self._pyz_entry_prefix = ''
            return
        self._pyz_entry_prefix = '.'.join(relative_path.split(os.path.sep))

    def _compute_pyz_entry_name(self, fullname):
        """
        Convert module fullname into PYZ entry name, subject to the prefix implied by this finder's search path.
        """

        tail_module = fullname.rpartition('.')[2]
        if self._pyz_entry_prefix:
            return self._pyz_entry_prefix + '.' + tail_module
        return tail_module

    @property
    def fallback_finder(self):
        '''
        Opportunistically create a *fallback finder* using `sys.path_hooks` entries that are located *after* our hook.
        The main goal of this exercise is to obtain an instance of python's FileFinder, but in theory any other hook
        that comes after ours is eligible to be a fallback.

        Having this fallback allows our finder to "cooperate" with python's FileFinder, as if the two were a single
        finder, which allows us to work around the python's PathFinder permitting only one finder instance per path
        without subclassing FileFinder.
        '''

        if hasattr(self, '_fallback_finder'):
            return self._fallback_finder
        our_hook_found = False
        self._fallback_finder = None
        for idx, hook in enumerate(sys.path_hooks):
            if hook == self.path_hook:
                our_hook_found = True
                continue
            if not our_hook_found:
                continue
            try:
                self._fallback_finder = hook(self._path)
            except ImportError:
                continue
            return self._fallback_finder
        return self._fallback_finder

    def _find_fallback_spec(self, fullname, target):
        '''
        Attempt to find the spec using fallback finder, which is opportunistically created here. Typically, this would
        be python's FileFinder, which can discover specs for on-filesystem modules, such as extension modules and
        modules that are collected only as source .py files.

        Having this fallback allows our finder to "cooperate" with python's FileFinder, as if the two were a single
        finder, which allows us to work around the python's PathFinder permitting only one finder instance per path
        without subclassing FileFinder.
        '''

        if not hasattr(self, '_fallback_finder'):
            self._fallback_finder = self._get_fallback_finder()
        if self._fallback_finder is None:
            return
        return self._fallback_finder.find_spec(fullname, target)

    def invalidate_caches(self):
        '''
        A method which, when called, should invalidate any internal cache used by the finder. Used by
        importlib.invalidate_caches() when invalidating the caches of all finders on sys.meta_path.

        https://docs.python.org/3/library/importlib.html#importlib.abc.MetaPathFinder.invalidate_caches
        '''

        fallback_finder = getattr(self, '_fallback_finder', None)
        if fallback_finder is not None and hasattr(fallback_finder, 'invalidate_caches'):
            fallback_finder.invalidate_caches()

    def find_spec(self, fullname, target=None):
        '''
        A method for finding a spec for the specified module. The finder will search for the module only within the
        path entry to which it is assigned. If a spec cannot be found, None is returned. When passed in, target is a
        module object that the finder may use to make a more educated guess about what spec to return.

        https://docs.python.org/3/library/importlib.html#importlib.abc.PathEntryFinder.find_spec
        '''

        trace(f'{self}: find_spec: called with fullname={fullname!r}, target={fullname!r}')
        pyz_entry_name = self._compute_pyz_entry_name(fullname)
        entry_data = self._pyz_archive.toc.get(pyz_entry_name)
        if entry_data is None:
            trace(f'{self}: find_spec: {fullname!r} not found in PYZ...')
            if self.fallback_finder is not None:
                trace(f'{self}: find_spec: attempting resolve using fallback finder {self.fallback_finder!r}.')
                fallback_spec = self.fallback_finder.find_spec(fullname, target)
                trace(f'{self}: find_spec: fallback finder returned spec: {fallback_spec!r}.')
                return fallback_spec
            trace(f'{self}: find_spec: fallback finder is not available.')
            return
        typecode = entry_data[0]
        trace(f'{self}: find_spec: found {fullname!r} in PYZ as {pyz_entry_name!r}, typecode={typecode}')
        if typecode == pyimod01_archive.PYZ_ITEM_NSPKG:
            spec = _frozen_importlib.ModuleSpec(fullname, None)
            spec.submodule_search_locations = [os.path.join(sys._MEIPASS, pyz_entry_name.replace('.', os.path.sep))]
            return spec
        is_package = typecode == pyimod01_archive.PYZ_ITEM_PKG
        loader = PyiFrozenLoader(name=fullname, pyz_archive=self._pyz_archive, pyz_entry_name=pyz_entry_name, is_package=is_package)
        origin = loader.path
        spec = _frozen_importlib.ModuleSpec(fullname, loader, is_package=is_package, origin=origin)
        spec.has_location = True
        if is_package:
            spec.submodule_search_locations = [os.path.dirname(origin)]
        return spec

    if sys.version_info[:2] < (3, 12):
        def find_loader(self, fullname):
            '''
            A legacy method for finding a loader for the specified module. Returns a 2-tuple of (loader, portion) where
            portion is a sequence of file system locations contributing to part of a namespace package. The loader may
            be None while specifying portion to signify the contribution of the file system locations to a namespace
            package. An empty list can be used for portion to signify the loader is not part of a namespace package. If
            loader is None and portion is the empty list then no loader or location for a namespace package were found
            (i.e. failure to find anything for the module).

            Deprecated since python 3.4, removed in 3.12.
            '''

            spec = self.find_spec(fullname)
            if spec is None:
                return None, []
            return spec.loader, spec.submodule_search_locations or []

        def find_module(self, fullname):
            '''
            A concrete implementation of Finder.find_module() which is equivalent to self.find_loader(fullname)[0].

            Deprecated since python 3.4, removed in 3.12.
            '''

            loader, portions = self.find_loader(fullname)
            return loader

        __static_attributes__ = ('_fallback_finder', '_path', '_pyz_archive', '_pyz_entry_prefix')

def _check_name(method):
    def _check_name_wrapper(self, name, *args, **kwargs):
        if self.name != name:
            raise ImportError(f'loader for {self.name} cannot handle {name}', name=name)
        return method(self, name, *args, **kwargs)

    return _check_name_wrapper

class PyiFrozenLoader:
    """
    PyInstaller's frozen loader for modules in the PYZ archive, which are discovered by PyiFrozenFinder.

    Since this loader is instantiated only from PyiFrozenFinder and since each loader instance is tied to a specific
    module, the fact that the loader was instantiated serves as the proof that the module exists in the PYZ archive.
    Hence, we can avoid any additional validation in the implementation of the loader's methods.
    """

    def __init__(self, name, pyz_archive, pyz_entry_name, is_package):
        self._pyz_archive = pyz_archive
        self._pyz_entry_name = pyz_entry_name
        self._is_package = is_package
        if is_package:
            module_file = os.path.join(sys._MEIPASS, pyz_entry_name.replace('.', os.path.sep), '__init__.py')
        else:
            module_file = os.path.join(sys._MEIPASS, pyz_entry_name.replace('.', os.path.sep) + '.py')
        self.name = name
        self.path = module_file

    def create_module(self, spec):
        '''
        A method that returns the module object to use when importing a module. This method may return None, indicating
        that default module creation semantics should take place.

        https://docs.python.org/3/library/importlib.html#importlib.abc.Loader.create_module
        '''

    def exec_module(self, module):
        '''
        A method that executes the module in its own namespace when a module is imported or reloaded. The module
        should already be initialized when exec_module() is called. When this method exists, create_module()
        must be defined.

        https://docs.python.org/3/library/importlib.html#importlib.abc.Loader.exec_module
        '''

        spec = module.__spec__
        bytecode = self.get_code(spec.name)
        if bytecode is None:
            raise RuntimeError(f'Failed to retrieve bytecode for {spec.name!r}!')
        assert hasattr(module, '__file__')
        if spec.submodule_search_locations is not None:
            module.__path__ = spec.submodule_search_locations
        exec(bytecode, module.__dict__)

    @_check_name
    def load_module(self, fullname):
        """
        A legacy method for loading a module. If the module cannot be loaded, ImportError is raised, otherwise the
        loaded module is returned.

        Deprecated since python 3.4, slated for removal in 3.12 (but still present in python's own FileLoader in
        both v3.12.4 and v3.13.0rc1).
        """

        import importlib._bootstrap as _bootstrap
        return _bootstrap._load_module_shim(self, fullname)

    @_check_name
    def get_filename(self, fullname):
        '''
        A method that is to return the value of __file__ for the specified module. If no path is available, ImportError
        is raised.

        If source code is available, then the method should return the path to the source file, regardless of whether a
        bytecode was used to load the module.

        https://docs.python.org/3/library/importlib.html#importlib.abc.ExecutionLoader.get_filename
        '''

        return self.path

    @_check_name
    def get_code(self, fullname):
        '''
        Return the code object for a module, or None if the module does not have a code object (as would be the case,
        for example, for a built-in module). Raise an ImportError if loader cannot find the requested module.

        https://docs.python.org/3/library/importlib.html#importlib.abc.InspectLoader.get_code
        '''

        return self._pyz_archive.extract(self._pyz_entry_name)

    @_check_name
    def get_source(self, fullname):
        """
        A method to return the source of a module. It is returned as a text string using universal newlines, translating
        all recognized line separators into '
' characters. Returns None if no source is available (e.g. a built-in
        module). Raises ImportError if the loader cannot find the module specified.

        https://docs.python.org/3/library/importlib.html#importlib.abc.InspectLoader.get_source
        """

        filename = self.path
        try:
            with open(filename, 'rb') as fp:
                source_bytes = fp.read()
        except FileNotFoundError:
            return
        return _decode_source(source_bytes)

    @_check_name
    def is_package(self, fullname):
        '''
        A method to return a true value if the module is a package, a false value otherwise. ImportError is raised if
        the loader cannot find the module.

        https://docs.python.org/3/library/importlib.html#importlib.abc.InspectLoader.is_package
        '''

        return self._is_package

    def get_data(self, path):
        '''
        A method to return the bytes for the data located at path. Loaders that have a file-like storage back-end that
        allows storing arbitrary data can implement this abstract method to give direct access to the data stored.
        OSError is to be raised if the path cannot be found. The path is expected to be constructed using a module’s
        __file__ attribute or an item from a package’s __path__.

        https://docs.python.org/3/library/importlib.html#importlib.abc.ResourceLoader.get_data
        '''

        with open(path, 'rb') as fp:
            return fp.read()

    @_check_name
    def get_resource_reader(self, fullname):
        '''
        Return resource reader compatible with `importlib.resources`.
        '''

        return PyiFrozenResourceReader(self)


class PyiFrozenResourceReader:
    """
Resource reader for importlib.resources / importlib_resources support.

Supports only on-disk resources, which should cover the typical use cases, i.e., the access to data files;
PyInstaller collects data files onto filesystem, and as of v6.0.0, the embedded PYZ archive is guaranteed
to contain only .pyc modules.

When listing resources, source .py files will not be listed as they are not collected by default. Similarly,
sub-directories that contained only .py files are not reconstructed on filesystem, so they will not be listed,
either. If access to .py files is required for whatever reason, they need to be explicitly collected as data files
anyway, which will place them on filesystem and make them appear as resources.

For on-disk resources, we *must* return path compatible with pathlib.Path() in order to avoid copy to a temporary
file, which might break under some circumstances, e.g., metpy with importlib_resources back-port, due to:
https://github.com/Unidata/MetPy/blob/a3424de66a44bf3a92b0dcacf4dff82ad7b86712/src/metpy/plots/wx_symbols.py#L24-L25
(importlib_resources tries to use 'fonts/wx_symbols.ttf' as a temporary filename suffix, which fails as it contains
a separator).

Furthermore, some packages expect files() to return either pathlib.Path or zipfile.Path, e.g.,
https://github.com/tensorflow/datasets/blob/master/tensorflow_datasets/core/utils/resource_utils.py#L81-L97
This makes implementation of mixed support for on-disk and embedded resources using importlib.abc.Traversable
protocol rather difficult.

So in order to maximize compatibility with unfrozen behavior, the below implementation is basically equivalent of
importlib.readers.FileReader from python 3.10:
  https://github.com/python/cpython/blob/839d7893943782ee803536a47f1d4de160314f85/Lib/importlib/readers.py#L11
and its underlying classes, importlib.abc.TraversableResources and importlib.abc.ResourceReader:
  https://github.com/python/cpython/blob/839d7893943782ee803536a47f1d4de160314f85/Lib/importlib/abc.py#L422
  https://github.com/python/cpython/blob/839d7893943782ee803536a47f1d4de160314f85/Lib/importlib/abc.py#L312
"""

    def __init__(self, loader):
        import pathlib
        self.path = pathlib.Path(loader.path).parent

    def open_resource(self, resource):
        return self.files().joinpath(resource).open('rb')

    def resource_path(self, resource):
        return str(self.path.joinpath(resource))

    def is_resource(self, path):
        return self.files().joinpath(path).is_file()

    def contents(self):
        return (item.name for item in self.files().iterdir())

    def files(self):
        return self.path


class PyiFrozenEntryPointLoader:
    '''
    A special loader that enables retrieval of the code-object for the __main__ module.
    '''

    def __repr__(self):
        return self.__class__.__name__

    def get_code(self, fullname):
        if fullname == '__main__':
            return sys.modules['__main__']._pyi_main_co
        raise ImportError(f'{self} cannot handle module {fullname!r}')


def install():
    """
    Install PyInstaller's frozen finders/loaders/importers into python's import machinery.
    """

    global pyz_archive
    if not hasattr(sys, '_pyinstaller_pyz'):
        raise RuntimeError('Bootloader did not set sys._pyinstaller_pyz!')
    try:
        pyz_archive = pyimod01_archive.ZlibArchiveReader(sys._pyinstaller_pyz, check_pymagic=True)
    except Exception as e:
        raise RuntimeError('Failed to setup PYZ archive reader!') from e
    delattr(sys, '_pyinstaller_pyz')
    for entry in sys.meta_path:
        if not getattr(entry, '__name__', None) == 'WindowsRegistryFinder':
            continue
        sys.meta_path.remove(entry)
        break
    for idx, entry in enumerate(sys.path_hooks):
        if not getattr(entry, '__name__', None) == 'zipimporter':
            continue
        trace(f'PyInstaller: inserting our finder hook at index {idx + 1} in sys.path_hooks.')
        sys.path_hooks.insert(idx + 1, PyiFrozenFinder.path_hook)
        break
    else:
        trace('PyInstaller: zipimporter hook not found in sys.path_hooks! Prepending our finder hook to the list.')
        sys.path_hooks.insert(0, PyiFrozenFinder.path_hook)
    _patch_zipimporter_get_source()
    sys.path_importer_cache.pop(sys._MEIPASS, None)
    try:
        sys.modules['__main__'].__loader__ = PyiFrozenEntryPointLoader()
    except Exception:
        pass
    if sys.version_info >= (3, 11):
        _fixup_frozen_stdlib()

def _fixup_frozen_stdlib():
    import _imp
    if not sys._stdlib_dir:
        try:
            sys._stdlib_dir = sys._MEIPASS
        except AttributeError:
            pass
    for module_name, module in sys.modules.items():
        if _imp.is_frozen(module_name):
            is_pkg = _imp.is_frozen_package(module_name)
            loader_state = module.__spec__.loader_state
            orig_name = loader_state.origname
            if is_pkg:
                orig_name += '.__init__'
            filename = os.path.join(sys._MEIPASS, *orig_name.split('.')) + '.pyc'
            if not hasattr(module, '__file__'):
                try:
                    module.__file__ = filename
                except AttributeError:
                    pass
            if loader_state.filename is None and orig_name != 'importlib._bootstrap':
                loader_state.filename = filename

def _patch_zipimporter_get_source():
    import zipimport
    _orig_get_source = zipimport.zipimporter.get_source
    def _get_source(self, fullname):
        source = _orig_get_source(self, fullname)
        if source is not None:
            return source
        if os.path.basename(self.archive) != 'base_library.zip':
            return
        if self.is_package(fullname):
            filename = os.path.join(*fullname.split('.'), '__init__.py')
        else:
            filename = os.path.join(*fullname.split('.')) + '.py'
        filename = os.path.join(_RESOLVED_TOP_LEVEL_DIRECTORY, filename)
        try:
            with open(filename, 'rb') as fp:
                source_bytes = fp.read()
        except FileNotFoundError:
            return
        return _decode_source(source_bytes)

    zipimport.zipimporter.get_source = _get_source

