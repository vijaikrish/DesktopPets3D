"""Where things live: the install root (code, web, pets) and the per-user data folder (settings, pet memories, logs)."""
import os
import sys

from . import APP_NAME


def install_root():
    """Folder that contains app/, web/, pets/. In a PyInstaller build this is the unpacked bundle."""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


ROOT = install_root()
WEB_DIR = os.path.join(ROOT, 'web')
PETS_DIR = os.path.join(ROOT, 'pets')


def _user_data_root():
    if sys.platform == 'win32':
        return os.environ.get('APPDATA') or os.path.expanduser('~')
    if sys.platform == 'darwin':
        return os.path.expanduser('~/Library/Application Support')
    return os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')


def data_dir():
    """Per-user writable folder: %APPDATA%\\DesktopPets3D (Windows), ~/Library/Application Support/DesktopPets3D
    (macOS), ~/.local/share/DesktopPets3D (Linux). Override with DP3D_DATA (tests use a temp folder)."""
    d = os.environ.get('DP3D_DATA') or os.path.join(_user_data_root(), APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def pet_data_dir(pet_id):
    d = os.path.join(data_dir(), 'pets', pet_id)
    os.makedirs(d, exist_ok=True)
    return d


def log_dir():
    d = os.path.join(data_dir(), 'logs')
    os.makedirs(d, exist_ok=True)
    return d


def log_path():
    return os.path.join(log_dir(), 'desktoppets3d.log')

