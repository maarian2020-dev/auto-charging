"""Recepcion del porcentaje de bateria de otros dispositivos por HTTP."""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("autocharging")


class RemoteStore:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def put(self, device, percent, plugged=None):
        with self._lock:
            self._data[device] = (time.time(), percent, plugged)

    def get_state(self, device, max_age):
        """(porcentaje, plugged) si el dato es reciente; si no, None."""
        with self._lock:
            item = self._data.get(device)
        if item and time.time() - item[0] <= max_age:
            return item[1], item[2]
        return None

    def get(self, device, max_age):
        state = self.get_state(device, max_age)
        return state[0] if state else None


def make_handler(store, token=""):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code, body):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            ok = self.path == "/health"
            self._reply(200 if ok else 404, {"ok": ok})

        def do_POST(self):
            if self.path != "/battery":
                return self._reply(404, {"error": "not found"})
            if token and self.headers.get("X-Token") != token:
                return self._reply(401, {"error": "token invalido"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                if not 0 < n <= 4096:
                    raise ValueError
                body = json.loads(self.rfile.read(n))
                device = str(body.get("device", "phone"))[:50]
                percent = float(body["percent"])
                if not 0 <= percent <= 100:
                    raise ValueError
                plugged = body.get("plugged")
                if plugged is not None and not isinstance(plugged, bool):
                    raise ValueError
            except (ValueError, KeyError, TypeError, AttributeError):
                return self._reply(400, {"error": "JSON esperado: {device, percent}"})
            store.put(device, percent, plugged)
            self._reply(200, {"ok": True})

        def log_message(self, *args):
            pass

    return Handler


def start_remote_server(cfg, store):
    server = ThreadingHTTPServer(("0.0.0.0", cfg.remote_port), make_handler(store, cfg.token))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not cfg.token:
        log.warning("REMOTE_TOKEN vacio: cualquiera en tu red podria enviar datos")
    log.info("Servidor remoto escuchando en el puerto %d", cfg.remote_port)
    return server
