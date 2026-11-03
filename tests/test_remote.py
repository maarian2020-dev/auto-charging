import http.client
import json
import threading
from http.server import ThreadingHTTPServer

from autocharging.remote import RemoteStore, make_handler


def _server(token=""):
    store = RemoteStore()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, token))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, store


def _post(srv, body, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
    conn.request("POST", "/battery", json.dumps(body), headers or {})
    return conn.getresponse().status


def test_accepts_valid_payload():
    srv, store = _server()
    assert _post(srv, {"device": "movil", "percent": 42}) == 200
    assert store.get("movil", 60) == 42.0
    srv.shutdown()


def test_rejects_bad_token_and_bad_values():
    srv, store = _server(token="secreto")
    assert _post(srv, {"device": "movil", "percent": 42}) == 401
    assert _post(srv, {"device": "movil", "percent": 142}, {"X-Token": "secreto"}) == 400
    assert store.get("movil", 60) is None
    srv.shutdown()
