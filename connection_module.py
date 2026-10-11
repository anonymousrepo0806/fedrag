from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class ConnectionModule:

    def call(self, method, path, data=None, ctype="application/octet-stream", retries=900):
        raise NotImplementedError

    def send_update(self, round_no, client_id, n, loss, blob):
        return self.call("POST", f"/update?round={round_no}&client={client_id}&n={n}&loss={loss}", blob)

    def get_model(self, after_round):
        return self.call("GET", f"/model?after_round={after_round}")

    def send_eval(self, round_no, client_id, payload):
        return self.call("POST", f"/eval?round={round_no}&client={client_id}", payload)


class HTTPConnectionModule(ConnectionModule):

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.sent = self.recv = 0

    def call(self, method, path, data=None, ctype="application/octet-stream", retries=900):
        if isinstance(data, (dict, list)):
            data, ctype = json.dumps(data).encode(), "application/json"
        for i in range(retries):
            try:
                req = urllib.request.Request(self.base + path, data=data, method=method,
                                             headers={"Content-Type": ctype})
                with urllib.request.urlopen(req, timeout=300) as r:
                    out = r.read()
                    self.sent += len(data or b"")
                    self.recv += len(out)
                    if r.status == 202:
                        continue
                    return out
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(min(5, 0.5 + i * 0.1))
        raise RuntimeError(f"{method} {path} failed")


class LocalConnectionModule(ConnectionModule):

    def __init__(self, server):
        self.server = server
        self.sent = self.recv = 0

    def call(self, method, path, data=None, ctype="application/octet-stream", retries=900):
        if isinstance(data, (dict, list)):
            data = json.dumps(data).encode()
        payload_len = len(data) if data else 0
        out = self.server.handle(method, path, data)
        self.sent += payload_len
        self.recv += len(out) if out else 0
        return out
