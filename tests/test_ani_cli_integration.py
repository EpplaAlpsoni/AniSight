import unittest

from ani_cli_integration import build_ani_cli_command, fetch_search_results, find_ani_cli


class AniCliIntegrationTests(unittest.TestCase):
    def test_find_ani_cli_returns_string(self):
        result = find_ani_cli()
        self.assertIsInstance(result, str)

    def test_build_ani_cli_command_uses_query(self):
        command = build_ani_cli_command("naruto")
        self.assertIn("ani-cli", command)
        self.assertIn("naruto", command)

    def test_fetch_search_results_returns_real_titles(self):
        results = fetch_search_results("naruto")
        self.assertTrue(results)
        self.assertTrue(any("naruto" in item["title"].lower() for item in results))


if __name__ == "__main__":
    unittest.main()
