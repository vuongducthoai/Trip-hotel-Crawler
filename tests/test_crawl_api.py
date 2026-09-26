import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import crawl_api


class CrawlApiTests(unittest.TestCase):
    def test_response_status_text_includes_result_id(self):
        payload = {
            "ResponseStatus": {
                "Ack": "Success",
                "Errors": [],
                "Extension": [{"id": "ResultId", "value": "201"}],
            }
        }

        summary = crawl_api._response_status_text(payload)

        self.assertIn("Ack=Success", summary)
        self.assertIn("Errors=[]", summary)
        self.assertIn("ResultId=201", summary)

    def test_response_status_text_handles_missing_status(self):
        summary = crawl_api._response_status_text({})

        self.assertIn("Ack=None", summary)
        self.assertNotIn("ResultId=", summary)

if __name__ == "__main__":
    unittest.main()
