# $Id$
#
# Author: Vasilis Vlachoudis
#  Email: Vasilis.Vlachoudis@cern.ch
#   Date: 16-Apr-2015

import gettext
import glob
import os
import sys
import traceback

from tkinter import (
    TclError,
    YES,
    N,
    W,
    E,
    EW,
    X,
    Y,
    BOTH,
    LEFT,
    TOP,
    RIGHT,
    BOTTOM,
    RAISED,
    VERTICAL,
    END,
    DISABLED,
    TkVersion,
    TclVersion,
    BooleanVar,
    Toplevel,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Scrollbar,
    Text,
    PhotoImage,
    LabelFrame,
    messagebox,
)
import tkinter.font as tkfont
import configparser


from lib.log import say

try:
    import serial
except Exception:
    serial = None

__author__ = "Vasilis Vlachoudis"
__email__ = "vvlachoudis@gmail.com"
__version__ = "0.9.17"
__date__ = "24 June 2022"
__prg__ = "bCNC"


__platform_fingerprint__ = "({} py{}.{}.{})".format(
    sys.platform,
    sys.version_info.major,
    sys.version_info.minor,
    sys.version_info.micro,
)
__title__ = f"{__prg__} {__version__} {__platform_fingerprint__}"

__prg__ = "bCNC"
prgpath = os.path.abspath(os.path.dirname(__file__))
if getattr(sys, "frozen", False):
    # When being bundled by pyinstaller, paths are different
    print("Running as pyinstaller bundle!", sys.argv[0])
    bundle_root = getattr(
        sys, "_MEIPASS", os.path.abspath(os.path.dirname(sys.executable))
    )
    package_root = os.path.join(bundle_root, __prg__)
    prgpath = package_root if os.path.isdir(package_root) else bundle_root
iniSystem = os.path.join(prgpath, f"{__prg__}.ini")
iniUser = os.path.expanduser(f"~/.{__prg__}")
hisFile = os.path.expanduser(f"~/.{__prg__}.history")


_ = gettext.translation(
    "bCNC", os.path.join(prgpath, "locale"), fallback=True
).gettext




__www__ = "https://github.com/vlachoudis/bCNC"
__contribute__ = (
    "@effer Filippo Rivato\n"
    "@carlosgs Carlos Garcia Saura\n"
    "@dguerizec\n"
    "@buschhardt\n"
    "@MARIOBASZ\n"
    "@harvie Tomas Mudrunka"
)
__credits__ = (
    "@1bigpig\n"
    "@chamnit Sonny Jeon\n"
    "@harvie Tomas Mudrunka\n"
    "@onekk Carlo\n"
    "@SteveMoto\n"
    "@willadams William Adams"
)
__translations__ = (
    "Dutch - @hypothermic\n"
    "French - @ThierryM\n"
    "German - @feistus, @SteveMoto\n"
    "Italian - @onekk\n"
    "Japanese - @stm32f1\n"
    "Korean - @jjayd\n"
    "Portuguese - @moacirbmn \n"
    "Russian - @minithc\n"
    "Simplified Chinese - @Bluermen\n"
    "Spanish - @carlosgs\n"
    "Traditional Chinese - @Engineer2Designer"
)

LANGUAGES = {
    "": "<system>",
    "de": "Deutsch",
    "en": "English",
    "es": "Espa\u00f1ol",
    "fr": "Fran\u00e7ais",
    "it": "Italiano",
    "ja": "Japanese",
    "kr": "Korean",
    "nl": "Nederlands",
    "pt_BR": "Brazilian - Portuguese",
    "ru": "Russian",
    "zh_cn": "Simplified Chinese",
    "zh_tw": "Traditional Chinese",
}

icons = {}
images = {}
config = configparser.ConfigParser(interpolation=None)
print(
    "new-config", __prg__, config
)  # This is here to debug the fact that config is sometimes instantiated twice
language = ""

_maxRecent = 10

_FONT_SECTION = "Font"


# -----------------------------------------------------------------------------
def loadIcons():
    global icons
    icons = {}
    for img in glob.glob(f"{prgpath}{os.sep}icons{os.sep}*.gif"):
        name, ext = os.path.splitext(os.path.basename(img))
        try:
            icons[name] = PhotoImage(file=img)
            if getBool("CNC", "doublesizeicon"):
                icons[name] = icons[name].zoom(2, 2)
        except TclError:
            pass

    # Images
    global images
    images = {}
    for img in glob.glob(f"{prgpath}{os.sep}images{os.sep}*.gif"):
        name, ext = os.path.splitext(os.path.basename(img))
        try:
            images[name] = PhotoImage(file=img)
            if getBool("CNC", "doublesizeicon"):
                images[name] = images[name].zoom(2, 2)
        except TclError:
            pass


# -----------------------------------------------------------------------------
def delIcons():
    global icons
    if len(icons) > 0:
        for i in icons.values():
            del i
        icons = {}  # needed otherwise it complains on deleting the icons

    global images
    if len(images) > 0:
        for i in images.values():
            del i
        images = {}  # needed otherwise it complains on deleting the icons


# -----------------------------------------------------------------------------
# Load configuration
# -----------------------------------------------------------------------------
def loadConfiguration(systemOnly=False):
    global config, language
    config = configparser.ConfigParser(interpolation=None)
    if systemOnly:
        config.read(iniSystem)
    else:
        config.read([iniSystem, iniUser])
        from PlotterPreferences import migrate_job_defaults
        migrate_job_defaults(config)

        language = getStr(__prg__, "language")
        if language and language != "en":
            # replace language
            lang = gettext.translation(
                __prg__,
                os.path.join(prgpath, "locales"),
                languages=[language]
            )
            lang.install()


# -----------------------------------------------------------------------------
# Save configuration file
# -----------------------------------------------------------------------------
def saveConfiguration():
    # Write a separate snapshot: saving must not erase live default values.
    import tempfile
    snapshot = cleanConfiguration()
    directory = os.path.dirname(os.path.abspath(iniUser))
    backup = iniUser + ".before-cleanup"
    if os.path.isfile(iniUser) and not os.path.exists(backup):
        import shutil
        shutil.copy2(iniUser, backup)
    fd, temporary = tempfile.mkstemp(prefix=".foil-config-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w") as stream:
            snapshot.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, iniUser)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    delIcons()


def cleanConfiguration():
    """Return overrides without retired UI/plugin settings; leave live data intact."""
    from copy import deepcopy
    from PlotterPreferences import used_option
    result = deepcopy(config)
    defaults = configparser.ConfigParser(interpolation=None)
    defaults.read(iniSystem)
    # Migrate values that still have consumers into their current sections.
    for editor in ('librecad', 'inkscape'):
        if config.has_option('File', editor) and not result.has_option('Editors', editor):
            if not result.has_section('Editors'):
                result.add_section('Editors')
            result.set('Editors', editor, config.get('File', editor))
    # Preserve the old overcut override before discarding plugin configuration.
    if config.has_option("DragKnife", "overcut") and not result.has_option("Plotter", "overcut"):
        if not result.has_section("Plotter"):
            result.add_section("Plotter")
        result.set("Plotter", "overcut", config.get("DragKnife", "overcut"))
    for section in result.sections():
        for key, value in list(result.items(section)):
            if (not used_option(defaults, section, key)
                    or (defaults.has_option(section, key) and defaults.get(section, key) == value)):
                result.remove_option(section, key)
        if not result.items(section):
            result.remove_section(section)
    return result


# -----------------------------------------------------------------------------
# add section if it doesn't exist
# -----------------------------------------------------------------------------
def addSection(section):
    global config
    if not config.has_section(section):
        config.add_section(section)


# -----------------------------------------------------------------------------
def getStr(section, name, default=""):
    global config
    try:
        return config.get(section, name)
    except Exception:
        return default


# -----------------------------------------------------------------------------
def getUtf(section, name, default=""):
    global config
    try:
        return config.get(section, name)
    except Exception:
        return default


# -----------------------------------------------------------------------------
def getInt(section, name, default=0):
    global config
    try:
        return int(config.get(section, name))
    except Exception:
        return default


# -----------------------------------------------------------------------------
def getFloat(section, name, default=0.0):
    global config
    try:
        return float(config.get(section, name))
    except Exception:
        return default


# -----------------------------------------------------------------------------
def getBool(section, name, default=False):
    global config
    try:
        return bool(int(config.get(section, name)))
    except Exception:
        return default


# -----------------------------------------------------------------------------
# Return a font from a string
# -----------------------------------------------------------------------------
def makeFont(name, value=None):
    try:
        font = tkfont.Font(name=name, exists=True)
    except TclError:
        font = tkfont.Font(name=name)
        font.delete_font = False
    except AttributeError:
        return None

    if value is None:
        return font

    if isinstance(value, tuple):
        font.configure(family=value[0])
        try:
            font.configure(size=value[1])
        except Exception:
            pass
        try:
            font.configure(weight=value[2])
        except Exception:
            pass
        try:
            font.configure(slant=value[3])
        except Exception:
            pass
    return font


# -----------------------------------------------------------------------------
# Create a font string
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Get font from configuration
# -----------------------------------------------------------------------------
def getFont(name, default=None):
    try:
        value = config.get(_FONT_SECTION, name)
    except Exception:
        value = None

    if not value:
        font = makeFont(name, default)
        setFont(name, font)
        return font

    if isinstance(value, str):
        value = tuple(value.split(","))

    if isinstance(value, tuple):
        font = makeFont(name, value)
        if font is not None:
            return font
    return value


# -----------------------------------------------------------------------------
# Set font in configuration
# -----------------------------------------------------------------------------
def setFont(name, font):
    if font is None:
        return
    if isinstance(font, str):
        config.set(_FONT_SECTION, name, font)
    elif isinstance(font, tuple):
        config.set(_FONT_SECTION, name, ",".join(map(str, font)))
    else:
        config.set(
            _FONT_SECTION,
            name,
            f"{font.cget('family')},{font.cget('size')},{font.cget('weight')}",
        )


# -----------------------------------------------------------------------------
def setBool(section, name, value):
    global config
    config.set(section, name, str(int(value)))


# -----------------------------------------------------------------------------
def setStr(section, name, value):
    global config
    config.set(section, name, str(value))


# -----------------------------------------------------------------------------
def setUtf(section, name, value):
    global config
    try:
        s = str(value)
    except Exception:
        s = value
    config.set(section, name, s)


setInt = setStr
setFloat = setStr


# -----------------------------------------------------------------------------
# Add Recent
# -----------------------------------------------------------------------------
def addRecent(filename):
    try:
        sfn = str(os.path.abspath(filename))
    except UnicodeEncodeError:
        sfn = filename

    last = _maxRecent - 1
    for i in range(_maxRecent):
        rfn = getRecent(i)
        if rfn is None:
            last = i - 1
            break
        if rfn == sfn:
            if i == 0:
                return
            last = i - 1
            break

    # Shift everything by one
    for i in range(last, -1, -1):
        config.set("File", f"recent.{i + 1}", getRecent(i))
    config.set("File", "recent.0", sfn)


# -----------------------------------------------------------------------------
def getRecent(recent):
    try:
        return config.get("File", f"recent.{int(recent)}")
    except configparser.NoOptionError:
        return None


# -----------------------------------------------------------------------------
# Return all comports when serial.tools.list_ports is not available!
# -----------------------------------------------------------------------------
def comports(include_links=True):
    locations = ["/dev/ttyACM", "/dev/ttyUSB", "/dev/ttyS", "com"]

    comports = []
    for prefix in locations:
        for i in range(32):
            device = f"{prefix}{i}"
            try:
                os.stat(device)
                comports.append((device, None, None))
            except OSError:
                pass

            # Detects windows XP serial ports
            try:
                s = serial.Serial(device)
                s.close()
                comports.append((device, None, None))
            except Exception:
                pass
    return comports
