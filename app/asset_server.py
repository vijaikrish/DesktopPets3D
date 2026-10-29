"""Read-only static file server on 127.0.0.1 (random port) for the pet windows.

Why a server: Chromium refuses ES modules and fetch() from file:// URLs. Only web/ and pets/ are served (no
directory listings, no path escapes); /qwebchannel.js is served from Qt's own resources.
"""
import logging
import mimetypes
import os
import posixpath
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)
TYPES = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary',
         '.wav': 'audio/wav', '.html': 'text/html', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg',
         '.svg': 'image/svg+xml', '.md': 'text/markdown'}


def _qwebchannel_js():
    from PySide6.QtCore import QFile, QIODevice
    f = QFile(':/qtwebchannel/qwebchannel.js')
    if not f.open(QIODevice.ReadOnly):
        raise RuntimeError('qwebchannel.js not found in Qt resources')
    data = bytes(f.readAll())
    f.close()
    return data


class AssetServer:
    def __init__(self, root, mounts=('web', 'pets')):
        self.root = os.path.abspath(root)
        self.mounts = set(mounts)
        self.virtual = {'/qwebchannel.js': (_qwebchannel_js(), 'text/javascript')}
        srv = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                srv._serve(self)

            def do_HEAD(self):
                srv._serve(self, head=True)

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name='asset-server', daemon=True)

    def start(self):
        self.thread.start()
        log.info('asset server on http://127.0.0.1:%d', self.port)
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path):
        return f'http://127.0.0.1:{self.port}{path}'

    def _resolve(self, url_path):
        p = posixpath.normpath(urllib.parse.unquote(url_path.split('?', 1)[0]))
        parts = [x for x in p.split('/') if x]
        if not parts or parts[0] not in self.mounts or any(x in ('..', '.') for x in parts):
            return None
        full = os.path.abspath(os.path.join(self.root, *parts))
        if not full.startswith(self.root + os.sep) or not os.path.isfile(full):
            return None
        return full

    def _serve(self, h, head=False):
        path = h.path.split('?', 1)[0]
        if path in self.virtual:
            data, ctype = self.virtual[path]
            return self._send(h, 200, data, ctype, head)
        full = self._resolve(path)
        if not full:
            return self._send(h, 404, b'not found', 'text/plain', head)
        ext = os.path.splitext(full)[1].lower()
        ctype = TYPES.get(ext) or mimetypes.guess_type(full)[0] or 'application/octet-stream'
        try:
            with open(full, 'rb') as f:
                data = f.read()
        except OSError:
            return self._send(h, 500, b'read error', 'text/plain', head)
        self._send(h, 200, data, ctype, head)

    @staticmethod
    def _send(h, code, data, ctype, head):
        try:
            h.send_response(code)
            h.send_header('Content-Type', ctype)
            h.send_header('Content-Length', str(len(data)))
            h.send_header('Cache-Control', 'no-cache')
            h.end_headers()
            if not head:
                h.wfile.write(data)
        except (ConnectionError, OSError):
            pass
