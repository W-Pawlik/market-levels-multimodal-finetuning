from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from market_levels.data_processing.real.binance_vision import archives, client


class TransferContracts(unittest.TestCase):
    def test_retry_then_atomic_download_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "nested/archive.zip"
            response = BytesIO(b"downloaded bytes")
            with patch.object(client, "urlopen", side_effect=[URLError("temporary"), response]) as network, patch.object(client.time, "sleep") as sleep:
                client._get("https://example.test/archive.zip", target, False)
                self.assertEqual(target.read_bytes(), b"downloaded bytes")
                self.assertFalse(target.with_suffix(".zip.part").exists())
                self.assertEqual(network.call_count, 2)
                self.assertEqual(network.call_args.kwargs, {"timeout": 35})
                self.assertEqual(network.call_args.args[0].get_header("User-agent"), client.USER_AGENT)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 0.15])
                client._get("https://example.test/archive.zip", target, True)
                self.assertEqual(network.call_count, 2)

    def test_http_retry_policy_and_partial_cleanup(self):
        url = "https://example.test/archive.zip"
        for code, attempts in ((404, 1), (403, 1), (429, 3), (503, 3)):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "archive.zip"
                part = target.with_suffix(".zip.part")
                part.write_bytes(b"partial")
                with patch.object(client, "urlopen", side_effect=HTTPError(url, code, "fixture", None, None)) as network, patch.object(client.time, "sleep"):
                    with self.assertRaises(client.DownloadError):
                        client._get(url, target, False)
                    self.assertEqual(network.call_count, attempts)
                    self.assertFalse(part.exists())
                    self.assertFalse(target.exists())

    def test_online_replaces_corrupt_cache_but_rejects_bad_download(self):
        from support.archives import make_archive
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, _ = make_archive(root)
            valid = path.read_bytes()
            path.write_bytes(b"corrupt")
            def restore(url, target, offline):
                if target == path:
                    self.assertFalse(target.exists())
                    target.write_bytes(valid)
            with patch.object(archives, "_get", side_effect=restore):
                archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", False)
            self.assertEqual(path.read_bytes(), valid)
            path.unlink()
            def bad_download(url, target, offline):
                if target == path:
                    target.write_bytes(b"wrong checksum")
            with patch.object(archives, "_get", side_effect=bad_download):
                with self.assertRaisesRegex(client.DownloadError, "Niezgodność SHA-256"):
                    archives.acquire_archive("BTCUSDT", "2024-01", "monthly", root / "raw", False)
