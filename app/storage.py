"""User settings + pet memory files. All writes are atomic (temp file + replace) so a crash never corrupts them."""
import json
import logging
import os
import tempfile
import time

from . import paths

log = logging.getLogger(__name__)

DEFAULTS = {
    'pets': {},                 # pet_id -> per-pet settings (below)
    'volume': 0.8,              # 0..1 master
    'muted': False,
    'quieter_when_away': True,  # -8 dB while you have been idle > 5 min (contact calls can be loud)
    'show_panel': False,        # mood panel (its own window)
    'panel_pos': None,          # [x, y] of the mood panel; None = beside the pet
}
PET_DEFAULTS = {
    'enabled': True,
    'variant': None,            # None = manifest default
    'size': None,               # S / M / L; None = manifest default
    'pos': None,                # [x, y] window top-left, screen px (None = bottom-right)
    'name': None,               # user's name for the pet (None = manifest name)
}


def write_json_atomic(path, data):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp_', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        log.exception('unreadable %s - keeping a copy and starting fresh', path)
        try:
            os.replace(path, path + f'.broken_{int(time.time())}')
        except OSError:
            pass
        return default


class Settings:
    def __init__(self):
        self.path = os.path.join(paths.data_dir(), 'settings.json')
        data = read_json(self.path, {}) or {}
        self.d = {**DEFAULTS, **data}

    def pet(self, pet_id):
        p = self.d['pets'].setdefault(pet_id, {})
        for k, v in PET_DEFAULTS.items():
            p.setdefault(k, v)
        return p

    def __getitem__(self, k):
        return self.d[k]

    def __setitem__(self, k, v):
        self.d[k] = v

    def save(self):
        write_json_atomic(self.path, self.d)


class PetMemory:
    """The pet's long-term memory on disk: engine.get_state() + a little bookkeeping."""

    def __init__(self, pet_id):
        self.path = os.path.join(paths.pet_data_dir(pet_id), 'state.json')

    def load(self):
        return read_json(self.path)

    def save(self, engine_state, extra=None):
        write_json_atomic(self.path, dict(saved_at=time.time(), engine=engine_state, **(extra or {})))
