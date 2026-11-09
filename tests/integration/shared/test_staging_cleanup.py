"""Blokady po publikacji i zachowanie pierwotnych wyjątków na Windows."""
import errno
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from market_levels.shared import publication as staging
from market_levels.data_processing.synthetic.workflows.generation import run
from market_levels.data_processing.synthetic.workflows.comparison import save_comparison
from market_levels.data_processing.synthetic.domain.profiles.v1 import diagnostic_profile
from market_levels.data_processing.synthetic.io.profiles import load_profile, save_profile
from market_levels.data_processing.synthetic.config.generation import SyntheticSettings
from market_levels.shared.json_io import write_json


def access_error():
    error = PermissionError(errno.EACCES, "simulated sharing violation")
    error.winerror = 32
    return error


class StagingCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = SyntheticSettings(generator_version="v2", diagnostic=True, count=1,
                                          symbols=("BTCUSDT",), output=self.root / "output")

    def test_published_batch_survives_permanent_access_error_with_warning(self):
        with patch.object(staging.shutil, "rmtree", side_effect=access_error()) as cleanup, \
                patch.object(staging.time, "sleep") as sleep, self.assertLogs(staging.LOGGER, "WARNING") as logs:
            final = run(self.settings)
        self.assertEqual(cleanup.call_count, 4)
        self.assertEqual(sleep.call_count, 3)
        manifest = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["accepted_count"], 1)
        self.assertTrue((final / manifest["examples"][0]["csv"]).is_file())
        wrappers = list(self.settings.output.glob(".synthetic-*"))
        self.assertEqual(len(wrappers), 1)
        self.assertEqual(list(wrappers[0].iterdir()), [])
        self.assertIn(str(wrappers[0]), logs.output[0])
        self.assertIn("wynik został opublikowany", logs.output[0])
        before = {p: p.read_bytes() for p in final.rglob("*") if p.is_file()}
        with self.assertRaises(FileExistsError):
            run(self.settings)
        self.assertEqual(before, {p: p.read_bytes() for p in final.rglob("*") if p.is_file()})

    def test_transient_access_error_is_retried_and_cleans_empty_wrapper(self):
        original = shutil.rmtree
        count = 0
        def intermittent(path):
            nonlocal count
            count += 1
            if count < 3:
                raise access_error()
            return original(path)
        with patch.object(staging.shutil, "rmtree", side_effect=intermittent), \
                patch.object(staging.time, "sleep") as sleep, patch.object(staging.LOGGER, "warning") as warn:
            final = run(self.settings)
        self.assertTrue((final / "manifest.json").is_file())
        self.assertEqual(count, 3)
        self.assertEqual(sleep.call_count, 2)
        warn.assert_not_called()
        self.assertEqual(list(self.settings.output.glob(".synthetic-*")), [])

    def test_original_generation_error_is_not_replaced_by_cleanup_error(self):
        error = ValueError("original generator failure")
        with patch('market_levels.data_processing.synthetic.workflows.generation.generate_example', side_effect=error), \
                patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING") as logs:
            with self.assertRaises(ValueError) as caught:
                run(self.settings)
        self.assertIs(caught.exception, error)
        self.assertEqual(list(self.settings.output.glob("diagnostics/*/manifest.json")), [])
        self.assertIn("zachowano pierwotny błąd", logs.output[0])
        self.assertNotIn("wynik został opublikowany", logs.output[0])

    def test_rename_failure_stays_failure_despite_cleanup_lock(self):
        error = access_error()
        with patch.object(Path, "rename", side_effect=error), \
                patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING"):
            with self.assertRaises(PermissionError) as caught:
                run(self.settings)
        self.assertIs(caught.exception, error)
        self.assertEqual(list(self.settings.output.glob("diagnostics/*/manifest.json")), [])

    def test_unrelated_cleanup_error_is_not_silently_accepted_after_publication(self):
        error = OSError(errno.EIO, "unexpected I/O failure")
        with patch.object(staging.shutil, "rmtree", side_effect=error) as cleanup, \
                patch.object(staging.time, "sleep") as sleep:
            with self.assertRaises(OSError) as caught:
                run(self.settings)
        self.assertIs(caught.exception, error)
        self.assertEqual(cleanup.call_count, 1)
        sleep.assert_not_called()

    def test_secondary_cleanup_errors_do_not_mask_original_error(self):
        for cleanup_error in (FileNotFoundError("entry disappeared"), RuntimeError("unexpected cleanup failure")):
            original = RuntimeError("operation failed")
            with patch.object(staging.shutil, "rmtree", side_effect=cleanup_error), \
                    self.assertLogs(staging.LOGGER, "WARNING"):
                with self.assertRaises(RuntimeError) as caught:
                    with staging.publication_workspace(self.root, prefix=".test-"):
                        raise original
            self.assertIs(caught.exception, original)

    def test_published_profile_survives_cleanup_lock_and_preserves_collision(self):
        path = self.root / "profile.json"
        profile = diagnostic_profile("BTCUSDT")
        with patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING"):
            save_profile(path, profile)
        self.assertEqual(load_profile(path), profile)
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            save_profile(path, profile)
        self.assertEqual(path.read_bytes(), before)

    def test_profile_write_error_remains_primary_when_cleanup_fails(self):
        path = self.root / "profile.json"
        error = OSError(errno.ENOSPC, "disk full")
        with patch('market_levels.data_processing.synthetic.io.profiles.write_json', side_effect=error), \
                patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING"):
            with self.assertRaises(OSError) as caught:
                save_profile(path, diagnostic_profile("BTCUSDT"))
        self.assertIs(caught.exception, error)
        self.assertFalse(path.exists())

    def test_published_report_survives_cleanup_lock_and_write_failure_stays_primary(self):
        report = {"comparison_id": "cleanup-fixture", "symbol": "BTCUSDT", "fixture": True}
        with patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING"):
            final = save_comparison(self.root / "reports", report, summary_text="fixture\n")
        self.assertEqual(json.loads((final / "BTCUSDT_comparison.json").read_text()), report)
        self.assertEqual((final / "BTCUSDT_summary.md").read_text(), "fixture\n")
        error = OSError(errno.ENOSPC, "report disk full")
        with patch('market_levels.data_processing.synthetic.workflows.comparison.write_json', side_effect=error), \
                patch.object(staging.shutil, "rmtree", side_effect=access_error()), \
                patch.object(staging.time, "sleep"), self.assertLogs(staging.LOGGER, "WARNING"):
            with self.assertRaises(OSError) as caught:
                save_comparison(self.root / "failed-report", report, summary_text="fixture\n")
        self.assertIs(caught.exception, error)
        self.assertFalse((self.root / "failed-report/cleanup-fixture").exists())

    @unittest.skipUnless(os.name == "nt", "Rzeczywista blokada uchwytu katalogu wymaga Windows")
    def test_real_windows_directory_lock_after_atomic_rename(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        original_write = write_json
        handle = None
        def lock_wrapper(path, document):
            nonlocal handle
            original_write(path, document)
            if path.name == "manifest.json":
                wrapper = path.parent.parent
                # GENERIC_READ, bez FILE_SHARE_DELETE: rename dziecka działa, rmdir rodzica nie.
                handle = kernel.CreateFileW(str(wrapper), 0x80000000, 3, None, 3, 0x02000000, None)
                if handle == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
        try:
            with patch('market_levels.data_processing.synthetic.workflows.generation.write_json', side_effect=lock_wrapper), \
                    self.assertLogs(staging.LOGGER, "WARNING") as logs:
                final = run(self.settings)
            self.assertTrue((final / "manifest.json").is_file())
            self.assertIn("wynik został opublikowany", logs.output[0])
            self.assertEqual(list(next(self.settings.output.glob(".synthetic-*")).iterdir()), [])
        finally:
            if handle is not None and handle != ctypes.c_void_p(-1).value:
                kernel.CloseHandle(handle)
