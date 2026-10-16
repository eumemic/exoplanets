"""The lock file: for every rule, the hash of the code, parameters and inputs it last ran with, and the hashes of the
outputs it wrote. It is committed, so anyone can see what each published file was built from, and a file whose
content differs from its entry here was changed outside the build."""
import json
import os
from pathlib import Path

VERSION = 1


class Lock:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"version": VERSION, "rules": {}}
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get("version") != VERSION:
                raise ValueError(f"{self.path}: lock version {self.data.get('version')}, expected {VERSION}")
        self._saved = self.text()

    def get(self, name):
        return self.data["rules"].get(name)

    def set(self, name, entry):
        self.data["rules"][name] = entry

    def remove(self, name):
        self.data["rules"].pop(name, None)

    def text(self):
        return json.dumps(self.data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    def save(self):
        t = self.text()
        if t != self._saved:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(t)
            os.replace(tmp, self.path)
            self._saved = t
