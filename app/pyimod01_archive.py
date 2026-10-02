import os
import struct
import marshal
import zlib
import _frozen_importlib
PYTHON_MAGIC_NUMBER = _frozen_importlib._bootstrap_external.MAGIC_NUMBER
PYZ_ITEM_MODULE = 0
PYZ_ITEM_PKG = 1
PYZ_ITEM_DATA = 2
PYZ_ITEM_NSPKG = 3

class ArchiveReadError(RuntimeError):
    pass

class ZlibArchiveReader:
    """
    Reader for PyInstaller's PYZ (ZlibArchive) archive. The archive is used to store collected byte-compiled Python
    modules, as individually-compressed entries.
    """

    _PYZ_MAGIC_PATTERN = b'PYZ\x00'
    def __init__(self, filename, start_offset=None, check_pymagic=False):
        self._filename = filename
        self._start_offset = start_offset
        self.toc = {}
        if start_offset is None:
            self._filename, self._start_offset = self._parse_offset_from_filename(filename)
        with open(self._filename, 'rb') as fp:
            fp.seek(self._start_offset, os.SEEK_SET)
            magic = fp.read(len(self._PYZ_MAGIC_PATTERN))
            if magic != self._PYZ_MAGIC_PATTERN:
                raise ArchiveReadError('PYZ magic pattern mismatch!')
            pymagic = fp.read(len(PYTHON_MAGIC_NUMBER))
            if check_pymagic and pymagic != PYTHON_MAGIC_NUMBER:
                raise ArchiveReadError('Python magic pattern mismatch!')
            toc_offset, *_ = struct.unpack('!i', fp.read(4))
            fp.seek(self._start_offset + toc_offset, os.SEEK_SET)
            self.toc = dict(marshal.load(fp))

    @staticmethod
    def _parse_offset_from_filename(filename):
        '''
        Parse the numeric offset from filename, stored as: `/path/to/file?offset`.
        '''

        offset = 0
        idx = filename.rfind('?')
        if idx == -1:
            return filename, offset
        try:
            offset = int(filename[idx + 1:])
            filename = filename[:idx]
        except ValueError:
            pass
        return filename, offset

    def extract(self, name, raw=False):
        '''
        Extract data from entry with the given name.

        If the entry belongs to a module or a package, the data is loaded (unmarshaled) into code object. To retrieve
        raw data, set `raw` flag to True.
        '''

        entry = self.toc.get(name)
        if entry is None:
            raise KeyError(f'No entry named {name!r} found in the archive!')
        typecode, entry_offset, entry_length = entry
        if typecode == PYZ_ITEM_NSPKG:
            return
        try:
            with open(self._filename, 'rb') as fp:
                fp.seek(self._start_offset + entry_offset)
                obj = fp.read(entry_length)
        except FileNotFoundError:
            raise SystemExit(f'ERROR: {self._filename} appears to have been moved or deleted since this application was launched. Continouation from this state is impossible. Exiting now.')
        try:
            obj = zlib.decompress(obj)
            if typecode in (PYZ_ITEM_MODULE, PYZ_ITEM_PKG) and not raw:
                obj = marshal.loads(obj)
        except EOFError as e:
            raise ImportError(f'Failed to unmarshal PYZ entry {name!r}!') from e
        return obj


