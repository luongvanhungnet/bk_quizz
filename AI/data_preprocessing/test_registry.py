import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import manage

class Registry(unittest.TestCase):
    def fixture(self,root):
        launcher=root/'entry';launcher.mkdir();release=root/'release';release.mkdir()
        (release/'worker.py').write_text('print(1)',encoding='utf-8')
        m={'version':'5.0.0','files':{'worker.py':manage.digest(release/'worker.py')}}
        (release/'RELEASE.json').write_text(json.dumps(m),encoding='utf-8')
        (launcher/'CURRENT.json').write_text(json.dumps({'release_path':'../release','release_manifest_sha256':manage.digest(release/'RELEASE.json')}),encoding='utf-8')
        return launcher,release
    def test_release_and_files_are_verified(self):
        with tempfile.TemporaryDirectory() as d:
            launcher,release=self.fixture(Path(d))
            with patch.object(manage,'ROOT',launcher):self.assertEqual(manage.selected_release()[0],release)
    def test_changed_release_code_blocks_execution(self):
        with tempfile.TemporaryDirectory() as d:
            launcher,release=self.fixture(Path(d));(release/'worker.py').write_text('print(2)',encoding='utf-8')
            with patch.object(manage,'ROOT',launcher),self.assertRaises(ValueError):manage.selected_release()
    def test_changed_release_manifest_blocks_execution(self):
        with tempfile.TemporaryDirectory() as d:
            launcher,release=self.fixture(Path(d));(release/'RELEASE.json').write_text('{}',encoding='utf-8')
            with patch.object(manage,'ROOT',launcher),self.assertRaises(ValueError):manage.selected_release()
    def test_operational_config_cannot_drift_silently(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);config={'pages_per_packet':100};(root/'config_snapshot.json').write_text(json.dumps(config),encoding='utf-8')
            manage.validate_plan_config(config,root)
            with self.assertRaises(ValueError):manage.validate_plan_config({'pages_per_packet':200},root)

if __name__=='__main__':unittest.main()
