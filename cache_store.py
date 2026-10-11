from __future__ import annotations

import hashlib
import json
import os
import pickle
import time


class CacheStore:
    def __init__(self, root):
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def _dir(self, namespace):
        d = os.path.join(self.root, namespace)
        os.makedirs(d, exist_ok=True)
        return d

    def _path(self, namespace, key):
        return os.path.join(self._dir(namespace), self._safe_key(key) + ".pkl")

    @staticmethod
    def _safe_key(key):
        if all(c.isalnum() or c in "-._" for c in key) and len(key) <= 120:
            return key
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def exists(self, namespace, key):
        return os.path.exists(self._path(namespace, key))

    def save(self, namespace, key, obj, meta=None):
        path = self._path(namespace, key)
        payload = {"namespace": namespace, "key": key, "saved_at": time.time(),
                   "meta": meta or {}, "data": obj}
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(payload, f, protocol=4)
        os.replace(tmp, path)
        return path

    def load(self, namespace, key, default=None):
        path = self._path(namespace, key)
        if not os.path.exists(path):
            return default
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return payload["data"]

    def load_raw_path(self, namespace, key):
        return self._path(namespace, key)

    def save_plain(self, namespace, key, obj):
        path = self._path(namespace, key)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(obj, f, protocol=4)
        os.replace(tmp, path)
        return path

    def load_plain(self, namespace, key, default=None):
        path = self._path(namespace, key)
        if not os.path.exists(path):
            return default
        with open(path, "rb") as f:
            return pickle.load(f)

    def delete(self, namespace, key):
        path = self._path(namespace, key)
        if os.path.exists(path):
            os.remove(path)

    def list_keys(self, namespace):
        d = self._dir(namespace)
        return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".pkl"))

    def stats(self):
        out = {}
        if not os.path.isdir(self.root):
            return out
        for namespace in sorted(os.listdir(self.root)):
            d = os.path.join(self.root, namespace)
            if not os.path.isdir(d):
                continue
            files = [f for f in os.listdir(d) if f.endswith(".pkl")]
            out[namespace] = {"entries": len(files),
                               "bytes": sum(os.path.getsize(os.path.join(d, f)) for f in files)}
        return out


class FileCacheHandle:

    def __init__(self, path):
        self.path = path

    def exists(self):
        return os.path.exists(self.path)

    def save_plain(self, obj):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(obj, f, protocol=4)
        os.replace(tmp, self.path)
        return self.path

    def load_plain(self, default=None):
        if not os.path.exists(self.path):
            return default
        with open(self.path, "rb") as f:
            return pickle.load(f)
