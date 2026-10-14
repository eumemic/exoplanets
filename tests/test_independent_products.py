import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.independent_products import fetch


class ManifestIntegrityTests(unittest.TestCase):
    def test_cached_product_must_match_manifest_digest(self):
        blob = b"SIMPLE  =                    T" + b" " * 2850
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            (out / "fits").mkdir()
            (out / "fits" / "sample.fits").write_bytes(blob)
            row = {"uri": "https://archive.stsci.edu/sample.fits",
                   "sha256": hashlib.sha256(blob).hexdigest()}
            with patch("pipeline.independent_products.requests.get") as request:
                self.assertEqual(fetch(row, out)["status"], "ok")
                with patch("pipeline.independent_products.time.sleep"):
                    result = fetch(dict(row, sha256="0" * 64), out)
                self.assertEqual(result["status"], "error")
                self.assertIn("SHA256 mismatch", result["error"])
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
