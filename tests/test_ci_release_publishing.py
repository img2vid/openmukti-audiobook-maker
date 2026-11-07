"""GitHub Release assets must be genuine, checksummed and correctly labelled."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_ci_release_assets import stage, EXPECTED_ARTIFACTS
from scripts.finalize_ci_release import summary


class ReleasePublicationTests(unittest.TestCase):
    def test_only_actual_packages_are_staged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'in'; source.mkdir()
            (source/'real.zip').write_bytes(b'abc')
            (source/'UNVERIFIED.zip').write_bytes(b'danger')
            (source/'build-report.json').write_text('{}')
            target=root/'out'
            result=stage(source,target,'Openmukti-Windows-x64')
            self.assertEqual([r['source'] for r in result],['real.zip'])
            self.assertTrue((target/'Openmukti-Windows-x64--real.zip').exists())
            self.assertFalse((target/'Openmukti-Windows-x64--UNVERIFIED.zip').exists())

    def test_oversized_files_are_split_without_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'in';source.mkdir()
            original=b'content larger than tiny test chunks'
            (source/'large.tar.gz').write_bytes(original)
            out=root/'out'
            records=stage(source,out,'Openmukti-Linux-x86_64',chunk_limit=7)
            parts=[r for r in records if 'file' in r]
            self.assertGreater(len(parts),1)
            self.assertEqual(b''.join((out/r['file']).read_bytes() for r in parts),original)
            full=next(r for r in records if 'source_checksum' in r)
            self.assertEqual(full['sha256'],hashlib.sha256(original).hexdigest())

    def test_partial_builds_are_never_labelled_complete(self):
        needs={'checks':{'result':'success'},
               'windows':{'result':'success'}, 'linux':{'result':'failure'}}
        result=summary(needs,['Openmukti-Windows-x64--output.zip'],
                       ref='refs/heads/main',run_url='https://example.invalid/run')
        self.assertFalse(result['complete'])
        self.assertTrue(result['prerelease'])
        self.assertIn('PARTIAL',result['title'])
        self.assertIn('Openmukti-Linux-x86_64',result['missing'])

    def test_verified_version_tag_requires_every_platform(self):
        needs={'checks':{'result':'success'},'linux':{'result':'success'}}
        assets=[name+'--valid.tar.gz' for name in EXPECTED_ARTIFACTS]
        value=summary(needs,assets,ref='refs/tags/v1.2.0',run_url='https://example.invalid/run')
        self.assertTrue(value['complete'])
        self.assertFalse(value['prerelease'])


    def test_release_upload_survives_skipped_optional_native_job(self):
        # In run #16 all required platforms passed, but the optional
        # additional-native-runners job was skipped. Without always() the
        # release-upload matrix was skipped as well.
        root = Path(__file__).resolve().parents[1]
        workflow = (root / '.github/workflows/build.yml').read_text(encoding='utf-8')
        create = workflow.split('  release-create:\n', 1)[1].split('  release-upload:\n', 1)[0]
        upload = workflow.split('  release-upload:\n', 1)[1].split('  release-finalize:\n', 1)[0]
        self.assertIn("if: ${{ always() && needs.release-create.result == 'success' }}",
                      upload)
        self.assertNotIn('--draft --prerelease', create)
        self.assertIn('              --prerelease', create)



if __name__=='__main__':
    unittest.main()
