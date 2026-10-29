"""Finds pet plugins (pets/<id>/pet.json), validates them and loads their emotion engines.

A folder is a pet plugin when it contains pet.json and its name does not start with '_' or '.'
(pets/_template is the copy-me starting point, not a pet).
"""
import importlib.util
import json
import logging
import os
import sys

from . import paths
from .clips import load_clip_table
from .plugin_api import API_VERSION, EngineContext, check_engine

log = logging.getLogger(__name__)
SCHEMA = 1
REQUIRED = ('id', 'name', 'model', 'engine', 'stage')


class PetSpec:
    """A validated pet plugin: manifest + resolved paths + clip table."""

    def __init__(self, pet_dir, manifest):
        self.dir = pet_dir
        self.m = manifest
        self.id = manifest['id']
        self.name = manifest['name']
        self.clips = load_clip_table(self.path(manifest['model']['clips']))

    def path(self, rel):
        return os.path.join(self.dir, *rel.replace('\\', '/').split('/'))

    def url(self, rel):
        """URL path of a plugin file on the local asset server."""
        return f'/pets/{os.path.basename(self.dir)}/{rel.replace(os.sep, "/")}'

    def variants(self):
        return dict(self.m['model']['variants'])

    def get(self, *keys, default=None):
        d = self.m
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    def create_engine(self, state_dir, seed=None, hour=12.0):
        e = self.m['engine']
        if int(e.get('api', 1)) != API_VERSION:
            raise RuntimeError(f'{self.id}: engine api {e.get("api")} != core api {API_VERSION}')
        pkg_dir = self.path(e.get('package', 'engine'))
        mod = _import_package(f'dp3d_pet_{self.id}_engine', pkg_dir)
        factory = getattr(mod, e.get('factory', 'create_engine'))
        ctx = EngineContext(pet_id=self.id, pet_dir=self.dir, manifest=self.m, clips=self.clips, data_dir=state_dir,
                            seed=seed, hour=hour, options=dict(e.get('options') or {}))
        return check_engine(factory(ctx))


def _import_package(name, pkg_dir):
    if name in sys.modules:
        return sys.modules[name]
    init = os.path.join(pkg_dir, '__init__.py')
    spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[pkg_dir])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        del sys.modules[name]
        raise
    return mod


def validate(pet_dir, m):
    """Return a list of problems (empty = OK)."""
    errs = []
    if m.get('schema', SCHEMA) != SCHEMA:
        errs.append(f'schema {m.get("schema")} unsupported (core reads {SCHEMA})')
    for k in REQUIRED:
        if k not in m:
            errs.append(f'missing "{k}"')
    if errs:
        return errs
    if m['id'] != os.path.basename(pet_dir):
        errs.append(f'id "{m["id"]}" must equal the folder name "{os.path.basename(pet_dir)}"')
    if not m['id'].isidentifier():
        errs.append('id must be a Python identifier (letters, digits, _)')

    def need(rel, what):
        if not rel or not os.path.exists(os.path.join(pet_dir, *rel.split('/'))):
            errs.append(f'{what}: file not found: {rel}')

    mod = m['model']
    for v, rel in (mod.get('variants') or {}).items():
        need(rel, f'model variant {v}')
    if not mod.get('variants'):
        errs.append('model.variants is empty')
    if mod.get('default_variant') not in (mod.get('variants') or {}):
        errs.append('model.default_variant must be one of model.variants')
    need(mod.get('clips'), 'model.clips')
    need(os.path.join(m['engine'].get('package', 'engine'), '__init__.py').replace(os.sep, '/'), 'engine package')
    snd = m.get('sounds') or {}
    if snd.get('bank'):
        need(snd['bank'], 'sounds.bank')
    if not errs:
        clips = load_clip_table(os.path.join(pet_dir, *mod['clips'].split('/')))
        for k in ('idle_clip',):
            c = m['stage'].get(k)
            if c and c not in clips:
                errs.append(f'stage.{k} "{c}" is not a clip')
    return errs


def discover(pets_dir=None):
    """All valid pet plugins, sorted by id. Invalid ones are logged and skipped."""
    pets_dir = pets_dir or paths.PETS_DIR
    out = []
    for name in sorted(os.listdir(pets_dir)):
        d = os.path.join(pets_dir, name)
        mp = os.path.join(d, 'pet.json')
        if name.startswith(('_', '.')) or not os.path.isfile(mp):
            continue
        try:
            with open(mp, encoding='utf-8') as f:
                m = json.load(f)
            errs = validate(d, m)
            if errs:
                log.error('pet %s skipped: %s', name, '; '.join(errs))
                continue
            out.append(PetSpec(d, m))
        except Exception:
            log.exception('pet %s failed to load', name)
    return out
