import unittest

from backend.app.main import app, cache, master_agent


class ApiContractTests(unittest.TestCase):
    def test_expected_routes_exist(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/health", paths)
        self.assertIn("/api/cache/stats", paths)
        self.assertIn("/api/analyze", paths)

    def test_master_agent_supports_api_payload_shape(self):
        response = master_agent.analyze(text="ERP SAP purchase order PO-900 material MAT-100 vendor code V-11")
        self.assertIn(response.document_type, {"ERP", "General Document"})
        self.assertIn("estimated_reduced_tokens", response.metrics)

    def test_cache_stats_contract(self):
        stats = cache.stats()
        self.assertIn("backend", stats)
        self.assertIn("hits", stats)
        self.assertIn("misses", stats)


if __name__ == "__main__":
    unittest.main()

