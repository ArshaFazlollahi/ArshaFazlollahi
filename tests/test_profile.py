import importlib.util
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("profile_generator", ROOT / "scripts/update_profile.py")
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class ProfileTests(unittest.TestCase):
    def test_cards_are_valid_xml_and_transparent(self):
        for name in ("stats", "languages", "hello"):
            for theme in ("light", "dark"):
                root = ET.parse(ROOT / f"profile/{name}-{theme}.svg").getroot()
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertNotIn('<script', ET.tostring(root, encoding="unicode"))
                self.assertFalse(any(rect.get("fill") not in (None, "none") and
                                     rect.get("width") in ("499", "500", "650")
                                     for rect in root.findall("{http://www.w3.org/2000/svg}rect")))

    def test_only_aggregate_fields_are_published(self):
        data = json.loads((ROOT / "profile/summary.json").read_text(encoding="utf-8"))
        self.assertNotIn("repos", data)
        self.assertNotIn("token", data)
        self.assertEqual(data["public_repositories"] + data["private_repositories"], data["repositories"])
        self.assertGreaterEqual(data["private_repositories"], 6)
        self.assertTrue(all(isinstance(value, int) and value > 0 for value in data["languages"].values()))

    def test_greeting_has_no_background(self):
        for theme in ("light", "dark"):
            root = ET.parse(ROOT / f"profile/hello-{theme}.svg").getroot()
            self.assertEqual(len(root.findall("{http://www.w3.org/2000/svg}rect")), 1)
            self.assertIn("Hello World, I'm Arsha!", (ROOT / f"profile/hello-{theme}.svg").read_text(encoding="utf-8"))

    def test_skill_badges_match_detected_data(self):
        data = json.loads((ROOT / "profile/summary.json").read_text(encoding="utf-8"))
        block = generator.skills_block(data)
        self.assertIn("Python", block)
        self.assertIn("TypeScript", block)
        self.assertIn("React", block)
        self.assertNotIn("Canva", block)
        self.assertEqual((ROOT / "README.md").read_text(encoding="utf-8").count("<!-- SKILLS:START -->"), 1)

    def test_no_token_is_a_safe_failure(self):
        with self.assertRaisesRegex(generator.ProfileError, "missing"):
            generator.GitHub("")

    def test_escaping_in_rendered_labels(self):
        data = json.loads((ROOT / "profile/summary.json").read_text(encoding="utf-8"))
        data["languages"] = {"<unsafe>": 100}
        output = generator.language_card(data, "light")
        self.assertIn("&lt;unsafe&gt;", output)
        ET.fromstring(output)

    def test_repository_pagination(self):
        class FakeAPI:
            def request(self, path):
                return [{}] * 100 if path.endswith("&page=1") else [{"private": True}]
        self.assertEqual(len(generator.owned_repositories(FakeAPI())), 101)

    def test_incomplete_private_access_fails_before_publication(self):
        class FakeAPI:
            def request(self, path):
                if path == "/user":
                    return {"login": generator.USERNAME, "owned_private_repos": 6}
                return [{"private": False}]
        with self.assertRaisesRegex(generator.ProfileError, "private repositories"):
            generator.collect(FakeAPI())


if __name__ == "__main__":
    unittest.main()
