"""A small fake of the part of the Kubernetes API that the Placement Controller uses (nodes: list, get, merge patch).

It checks the bearer token, applies JSON merge-patch semantics (null deletes a key, lists are replaced) and answers
409 when the patch carries a stale resourceVersion, as the real API does. It is a test double, not Kubernetes.
Run it standalone: `python tests/fake_k8s.py 8001`.
"""
import copy
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def merge_patch(target, patch):
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    out = dict(target) if isinstance(target, dict) else {}
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge_patch(out.get(k), v)
    return out


def node(name, pool, ready=True):
    return {"metadata": {"name": name, "labels": {"energy-pool": pool}, "resourceVersion": "1"}, "spec": {},
            "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


class FakeK8s:
    def __init__(self, nodes, token="test-token"):
        self.nodes = {n["metadata"]["name"]: n for n in nodes}
        self.token, self.requests, self.fail_next_patch = token, [], 0
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _send(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def _handle(self, method):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                with owner.lock:
                    owner.requests.append((method, self.path, body, self.headers.get("Content-Type")))
                    if self.headers.get("Authorization") != f"Bearer {owner.token}":
                        return self._send(401, {"message": "Unauthorized"})
                    if self.path == "/api/v1/nodes" and method == "GET":
                        return self._send(200, {"items": [copy.deepcopy(x) for x in owner.nodes.values()]})
                    if self.path.startswith("/api/v1/nodes/"):
                        name = self.path.rsplit("/", 1)[1]
                        cur = owner.nodes.get(name)
                        if cur is None:
                            return self._send(404, {"message": f"nodes {name} not found"})
                        if method == "GET":
                            return self._send(200, copy.deepcopy(cur))
                        if method == "PATCH":
                            if owner.fail_next_patch:
                                owner.fail_next_patch -= 1
                                return self._send(403, {"message": "forbidden"})
                            rv = (body.get("metadata") or {}).get("resourceVersion")
                            if rv is not None and rv != cur["metadata"]["resourceVersion"]:
                                return self._send(409, {"message": "the object has been modified"})
                            new = merge_patch(cur, {k: v for k, v in body.items() if k != "metadata"})
                            new["metadata"]["resourceVersion"] = str(int(cur["metadata"]["resourceVersion"]) + 1)
                            owner.nodes[name] = new
                            return self._send(200, copy.deepcopy(new))
                    self._send(404, {"message": "not found"})

            def do_GET(self): self._handle("GET")
            def do_PATCH(self): self._handle("PATCH")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        self.server.shutdown(); self.server.server_close()

    def taints(self, name):
        return self.nodes[name].get("spec", {}).get("taints")


if __name__ == "__main__":
    k = FakeK8s([node("s1", "standard"), node("e1", "eco")]).start()
    print("fake Kubernetes API on", k.url, "token", k.token, flush=True)
    threading.Event().wait()
