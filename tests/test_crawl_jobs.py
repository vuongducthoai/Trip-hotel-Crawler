import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import crawl_jobs


class JobHistoryTests(unittest.TestCase):
    def test_lich_su_duoc_luu_va_doc_lai(self):
        old_path = crawl_jobs.HISTORY_PATH
        try:
            with tempfile.TemporaryDirectory() as folder:
                crawl_jobs.HISTORY_PATH = Path(folder) / "lich_su.json"
                runner = crawl_jobs.JobRunner()
                runner.history.appendleft({"label": "Kiểm tra", "returncode": 0})
                runner._save_history()

                restored = crawl_jobs.JobRunner()
                self.assertEqual(restored.history[0]["label"], "Kiểm tra")
        finally:
            crawl_jobs.HISTORY_PATH = old_path


if __name__ == "__main__":
    unittest.main()
