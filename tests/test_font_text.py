import glob
import os
import sys
import unittest

BCNC = os.path.join(os.path.dirname(__file__), "..", "bCNC")
LIB = os.path.join(BCNC, "lib")
for path in (BCNC, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

import font_text
from font_text import text_to_paths


FONTS = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
FONT = next(
    (path for path in FONTS if path.endswith("DejaVuSans.ttf")),
    FONTS[0] if FONTS else None,
)


@unittest.skipUnless(FONT, "No system TTF font is available")
class FontTextTest(unittest.TestCase):
    def test_generates_closed_vector_contours(self):
        paths = text_to_paths("bCNC", FONT, 10.0)
        self.assertTrue(paths)
        self.assertTrue(all(path.isClosed() for path in paths))
        self.assertTrue(all(len(path) >= 3 for path in paths))

    def test_preserves_glyph_counters(self):
        paths = text_to_paths("O", FONT, 10.0)
        self.assertGreaterEqual(len(paths), 2)

    def test_supports_multiline_text(self):
        paths = text_to_paths("A\nB", FONT, 10.0)
        ymin = min(segment.miny for path in paths for segment in path)
        ymax = max(segment.maxy for path in paths for segment in path)
        self.assertLess(ymin, 0.0)
        self.assertGreater(ymax, 0.0)

    def test_rejects_empty_text(self):
        with self.assertRaises(ValueError):
            text_to_paths("", FONT, 10.0)

    def test_rejects_nonpositive_height(self):
        with self.assertRaises(ValueError):
            text_to_paths("Text", FONT, 0.0)

    def test_shapely_is_optional(self):
        saved = font_text.unary_union
        font_text.unary_union = None
        try:
            paths = text_to_paths("Text", FONT, 10.0)
        finally:
            font_text.unary_union = saved
        self.assertTrue(paths)
        self.assertTrue(all(path.isClosed() for path in paths))


if __name__ == "__main__":
    unittest.main()
