"""Process-local registration of the bundled workspace font family."""
import ctypes
from ctypes.util import find_library
import os
from pathlib import Path
import sys
import Utils


FONT_FILES = ('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf')
FONT_DIR = Path(Utils.prgpath) / 'fonts'
_registered = False


def register_fonts():
    global _registered
    if _registered:
        return
    paths = [FONT_DIR / filename for filename in FONT_FILES]
    for path in paths:
        if not path.is_file():
            raise OSError(f'Missing bundled UI font: {path}')
    if sys.platform == 'win32':
        library = ctypes.WinDLL('gdi32')
        register = library.AddFontResourceExW
        register.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
        register.restype = ctypes.c_int
        for path in paths:
            if not register(str(path), 0x10, None):
                raise OSError(f'Cannot register private UI font: {path}')
    elif sys.platform == 'darwin':
        foundation = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        coretext = ctypes.CDLL('/System/Library/Frameworks/CoreText.framework/CoreText')
        create_url = foundation.CFURLCreateFromFileSystemRepresentation
        create_url.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool]
        create_url.restype = ctypes.c_void_p
        release = foundation.CFRelease
        release.argtypes = [ctypes.c_void_p]
        release.restype = None
        register = coretext.CTFontManagerRegisterFontsForURL
        register.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        register.restype = ctypes.c_bool
        for path in paths:
            encoded = os.fsencode(path)
            url = create_url(None, encoded, len(encoded), False)
            if not url:
                raise OSError(f'Cannot create UI font URL: {path}')
            try:
                if not register(url, 1, None):
                    raise OSError(f'Cannot register process UI font: {path}')
            finally:
                release(url)
    else:
        name = find_library('fontconfig')
        if not name:
            raise OSError('Fontconfig is required to register bundled UI fonts')
        library = ctypes.CDLL(name)
        register = library.FcConfigAppFontAddFile
        register.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        register.restype = ctypes.c_int
        for path in paths:
            if not register(None, os.fsencode(path)):
                raise OSError(f'Cannot register application UI font: {path}')
    _registered = True