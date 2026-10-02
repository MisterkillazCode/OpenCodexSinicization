def _pyi_bootstrap():
    import sys
    import os
    import pyimod02_importers
    pyimod02_importers.install()
    if not hasattr(sys, 'frozen'):
        sys.frozen = True
    VIRTENV = 'VIRTUAL_ENV'
    if VIRTENV in os.environ:
        os.environ[VIRTENV] = ''
        del os.environ[VIRTENV]
    try:
        import encodings
    except ImportError:
        encodings = None
    if encodings and hasattr(encodings, '__path__'):
        encodings_dir = os.path.join(sys._MEIPASS, 'base_library.zip', 'encodings')
        if encodings_dir not in encodings.__path__:
            encodings.__path__.append(encodings_dir)
    if sys.warnoptions:
        try:
            import warnings
        except ImportError:
            pass
    import pyimod03_ctypes
    pyimod03_ctypes.install()
    if sys.platform.startswith('win'):
        import pyimod04_pywin32
        pyimod04_pywin32.install()
    for entry in os.listdir(sys._MEIPASS):
        entry = os.path.join(sys._MEIPASS, entry)
        if os.path.isdir(entry) and entry.endswith('.egg'):
            sys.path.append(entry)

_pyi_bootstrap()
del _pyi_bootstrap
