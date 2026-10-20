import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from theia import paths


class ModelFolderTests(unittest.TestCase):
    def tearDown(self):
        paths.models_root.cache_clear()
        paths._env.cache_clear()

    def test_configured_generated_model_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text('THEIA_MODELS_PATH="~/generated-models"\n', encoding="utf-8")
            with patch.object(paths, "_PROJECT_ROOT", root), patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in {"DATA_PATH", "THEIA_MODELS_PATH"}}, clear=True):
                paths.models_root.cache_clear()
                paths._env.cache_clear()
                self.assertEqual(paths.models_root(), Path.home() / "generated-models")
                with patch.dict(os.environ, {"THEIA_MODELS_PATH": str(root / "selected")}):
                    paths.models_root.cache_clear()
                    self.assertEqual(paths.models_root(), root / "selected")

    def test_source_neutral_default_and_data_root_override(self):
        with patch.dict(os.environ, {k: v for k, v in os.environ.items() if k not in {"DATA_PATH", "THEIA_MODELS_PATH"}}, clear=True), patch.object(paths, "_env", return_value={}):
            paths.models_root.cache_clear()
            self.assertEqual(paths.models_root(), Path.home() / "Documents" / "Theia" / "models")
            with patch.dict(os.environ, {"DATA_PATH": str(Path.home() / "data")}):
                paths.models_root.cache_clear()
                self.assertEqual(paths.models_root(), Path.home() / "data" / "models")


if __name__ == "__main__":
    unittest.main()
