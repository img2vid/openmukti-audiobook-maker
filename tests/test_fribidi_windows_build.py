"""Portable Windows text-shaping build regression tests, no network needed."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import struct
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fribidi_bundle', ROOT / 'packaging/fribidi_bundle.py')
fribidi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fribidi)


def fake_pe(machine):
    header=bytearray(128)
    header[:2]=b'MZ'
    struct.pack_into('<I',header,0x3c,0x40)
    header[0x40:0x44]=b'PE\0\0'
    struct.pack_into('<H',header,0x44,machine)
    return bytes(header)


def uncompressed_archive(prefix, machine):
    binary=io.BytesIO()
    with tarfile.open(fileobj=binary,mode='w') as tar:
        for path,data in [(f'{prefix}/bin/libfribidi-0.dll',fake_pe(machine)),
                          (f'{prefix}/share/licenses/fribidi/COPYING',b'LGPL license fixture')]:
            member=tarfile.TarInfo(path)
            member.size=len(data)
            tar.addfile(member,io.BytesIO(data))
    return binary.getvalue()


class WindowsFriBidiTests(unittest.TestCase):
    def test_has_separate_verified_packages_for_x64_and_arm64(self):
        a=fribidi.PACKAGES
        self.assertEqual(set(a),{'x86_64','aarch64'})
        self.assertEqual(a['x86_64']['machine'],0x8664)
        self.assertEqual(a['aarch64']['machine'],0xaa64)
        for name,values in a.items():
            self.assertEqual(len(values['sha256']),64)
            self.assertTrue(values['url'].startswith('https://mirror.msys2.org/'))

    def test_extract_only_dll_and_license_from_trusted_tar(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for arch,config in fribidi.PACKAGES.items():
                with self.subTest(architecture=arch):
                    source=uncompressed_archive(config['prefix'],config['machine'])
                    with patch.object(fribidi,'_zstd_stream',return_value=io.BytesIO(source)):
                        fribidi._extract(folder/'unused.zst',folder/arch,config)
                    self.assertEqual(fribidi._pe_machine(folder/arch/'libfribidi-0.dll'),config['machine'])
                    self.assertEqual(sorted(x.name for x in (folder/arch).iterdir()),
                                     ['FRIBIDI-LICENSE.txt','libfribidi-0.dll'])

    def test_rejects_wrong_architecture_without_falling_back_to_broken_shaping(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'x86_64'
            folder.mkdir(parents=True)
            config=fribidi.PACKAGES['x86_64']
            with patch.dict(config,sha256=hashlib.sha256(b'fixture').hexdigest()):
                (folder/'fribidi-1.0.17-1.pkg.tar.zst').write_bytes(b'fixture')
                (folder/'libfribidi-0.dll').write_bytes(fake_pe(0xaa64))
                (folder/'FRIBIDI-LICENSE.txt').write_bytes(b'license')
                with self.assertRaisesRegex(RuntimeError,'wrong PE architecture'):
                    fribidi.prepare('x86_64',Path(temp))
                self.assertFalse((folder/'libfribidi-0.dll').exists())

    def test_rejects_archive_with_invalid_sha256(self):
        with tempfile.TemporaryDirectory() as temp:
            filename=Path(temp)/'download.pkg.tar.zst'
            class FakeResponse(io.BytesIO):
                pass
            with patch.object(fribidi.urllib.request,'urlopen',return_value=FakeResponse(b'fake archive')):
                with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
                    fribidi._download('https://mirror.msys2.org/example',filename,'a'*64)
            self.assertFalse(filename.exists())
            self.assertFalse(list(Path(temp).glob('*.partial')))

    def test_pillow_frozen_builder_includes_native_dll_and_license(self):
        src=(ROOT/'packaging/build_release.py').read_text()
        self.assertIn("'--add-binary', str(dll) + os.pathsep + 'text_layout'",src)
        self.assertIn("'--add-data', str(license_file) + os.pathsep + 'text_layout'",src)
        for name in ('openvoice_gui.py','openvoice_cli.py'):
            source=(ROOT/name).read_text()
            self.assertLess(source.index('_configure_windows_text_libraries()'),
                            source.index('from openvoice.' + ('gui' if 'gui' in name else 'cli') + ' import main'))


if __name__=='__main__':
    unittest.main()
