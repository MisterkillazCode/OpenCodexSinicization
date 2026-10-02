def _pyi_rthook():
    import inspect
    import os
    import sys
    import zipfile
    SYS_PREFIX = os.path.normpath(sys._MEIPASS)
    BASE_LIBRARY = os.path.join(SYS_PREFIX, 'base_library.zip')
    def _get_base_library_files(filename):
        if not os.path.isfile(filename):
            return set()
        with zipfile.ZipFile(filename, 'r') as zf:
            namelist = zf.namelist()
        return set((os.path.normpath(entry) for entry in namelist))

    base_library_files = _get_base_library_files(BASE_LIBRARY)
    _orig_inspect_getsourcefile = inspect.getsourcefile
    def _pyi_getsourcefile(object):
        filename = inspect.getfile(object)
        filename = os.path.normpath(filename)
        if not os.path.isabs(filename):
            main_file = getattr(sys.modules['__main__'], '__file__', None)
            if main_file and filename == os.path.basename(main_file):
                return main_file
            pyc_filename = filename + 'c'
            if pyc_filename in base_library_files:
                return os.path.normpath(os.path.join(BASE_LIBRARY, pyc_filename))
            return os.path.normpath(os.path.join(SYS_PREFIX, filename))
        if filename.startswith(SYS_PREFIX):
            return filename
        return _orig_inspect_getsourcefile(object)

    inspect.getsourcefile = _pyi_getsourcefile

_pyi_rthook()
del _pyi_rthook
