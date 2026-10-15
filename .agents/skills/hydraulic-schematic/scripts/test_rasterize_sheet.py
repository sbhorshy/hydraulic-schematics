"""Readback freshness and 1:1 coordinate contracts; real browser acceptance is separate."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rasterize_sheet as R


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.svg = Path(self.tmp.name, 'sheet.svg')
        self.png = Path(self.tmp.name, 'readback.png')
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 160"/>')
        self.png.write_bytes(b'old stale image')

    def test_scaled_image_rejected_and_old_readback_removed(self):
        with self.assertRaisesRegex(ValueError, 'viewBox'):
            R.export(self.svg, self.png, width=400)
        self.assertFalse(self.png.exists())

    def test_missing_renderer_does_not_leave_old_readback(self):
        with patch.object(R.shutil, 'which', return_value=None), patch.object(R.os.path, 'isfile', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '缺少'):
                R.export(self.svg, self.png)
        self.assertFalse(self.png.exists())

    def test_nonzero_origin_rejected_for_pixel_probes(self):
        self.svg.write_text('<svg viewBox="20 10 200 160"/>')
        with self.assertRaisesRegex(ValueError, 'viewBox'):
            R.export(self.svg, self.png)
        self.assertFalse(self.png.exists())

    def test_input_svg_cannot_be_overwritten(self):
        original = self.svg.read_bytes()
        with self.assertRaisesRegex(ValueError, '覆盖'):
            R.export(self.svg, self.svg)
        self.assertEqual(self.svg.read_bytes(), original)

    def test_backend_fallback_uses_available_chrome(self):
        with patch.object(R.shutil, 'which', side_effect=lambda name: '/bin/google-chrome' if name == 'google-chrome' else None):
            with patch.object(R.os.path, 'isfile', return_value=False):
                self.assertEqual(R.renderer(), ('chrome', '/bin/google-chrome'))

    def test_wrong_size_renderer_output_is_not_published(self):
        import struct
        def wrong_image(cmd, **kwargs):
            output = next(x.split('=', 1)[1] for x in cmd if x.startswith('--screenshot='))
            Path(output).write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 400, 320))
            return type('Completed', (), {'returncode': 0, 'stderr': ''})()
        with patch.object(R, 'renderer', return_value=('chrome', '/bin/chrome')):
            with patch.object(R.subprocess, 'run', side_effect=wrong_image):
                with self.assertRaisesRegex(RuntimeError, '尺寸'):
                    R.export(self.svg, self.png)
        self.assertFalse(self.png.exists())


if __name__ == '__main__':
    unittest.main()
