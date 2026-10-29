import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

class DependencyMigrationTests(unittest.TestCase):
    def test_current_release_has_verified_self_contained_dependencies(self):
        current = json.loads((ROOT/'CURRENT.json').read_text(encoding='utf-8'))
        self.assertEqual(current['version'], '5.0.1')
        release = (ROOT/current['release_path']).resolve()
        manifest = json.loads((ROOT/'DEPENDENCY_MIGRATION.json').read_text(encoding='utf-8'))
        for entry in manifest['copied_files']:
            path = ROOT.parent.parent/entry['destination']
            self.assertTrue(path.is_file(), str(path))
            with path.open('rb') as stream:
                self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), entry['sha256'], str(path))
        self.assertTrue((release/'dependency_paths.py').is_file())

if __name__ == '__main__': unittest.main()
