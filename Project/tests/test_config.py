import os
import unittest

from meeting_translator.config import Settings
from tests.helpers import TempDir


class SettingsTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        s = Settings({})
        self.assertEqual(s.api_key, "")
        self.assertEqual(s.input_dir, "input")
        s = Settings({"GEMINI_API_KEY": "  abc  ", "GEMMA_MODEL": "m", "DATA_FILE": "x.csv"})
        self.assertEqual((s.api_key, s.model, s.data_path), ("abc", "m", "x.csv"))

    def test_env_file_parsing_and_environment_wins(self):
        with TempDir() as folder:
            path = os.path.join(folder, ".env")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('# comment\nGEMINI_API_KEY="from-file"\nexport GEMMA_MODEL=file-model\nbad line\nEMPTY=\n')
            saved_env = {k: os.environ.pop(k, None) for k in ("GEMINI_API_KEY", "GEMMA_MODEL")}
            os.environ["GEMMA_MODEL"] = "from-env"
            try:
                s = Settings.from_environment(path)
            finally:
                del os.environ["GEMMA_MODEL"]
                for key, value in saved_env.items():
                    if value is not None:
                        os.environ[key] = value
            self.assertEqual(s.model, "from-env")       # real environment beats the file
            self.assertEqual(s.api_key, "from-file")    # the file fills the gaps

    def test_whisper_model_defaults_to_base_and_can_be_changed(self):
        self.assertEqual(Settings({}).whisper_model, "base")
        self.assertEqual(Settings({"WHISPER_MODEL": " small "}).whisper_model, "small")
        self.assertEqual(Settings({"WHISPER_MODEL": "   "}).whisper_model, "base")

    def test_missing_env_file_is_fine(self):
        self.assertIsInstance(Settings.from_environment(os.path.join("no", "such", ".env")), Settings)


if __name__ == "__main__":
    unittest.main()
