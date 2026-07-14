import os
import sys
import unittest

import numpy as np
from PIL import Image

BCNC = os.path.join(os.path.dirname(__file__), "..", "bCNC")
LIB = os.path.join(BCNC, "lib")
for path in (BCNC, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

from imagetrace import (
    contours,
    foreground_mask,
    multi_threshold_masks,
    print_then_cut_contour,
    skeleton_paths,
    trace_image,
    zhang_suen,
)


class ImageTraceTest(unittest.TestCase):
    def test_background_removal_keeps_coloured_artwork(self):
        pixels = np.full((9, 9, 4), (255, 255, 255, 255), dtype=np.uint8)
        pixels[3:6, 3:6] = (20, 80, 220, 255)
        mask = foreground_mask(Image.fromarray(pixels, "RGBA"), tolerance=24)
        self.assertEqual(int(mask.sum()), 9)

    def test_print_then_cut_returns_one_external_loop(self):
        mask = np.zeros((30, 30), dtype=np.uint8)
        mask[3:12, 3:12] = 1
        mask[18:27, 18:27] = 1
        loop = print_then_cut_contour(mask, minimum_area=1, simplify=0)
        self.assertEqual(len(loop), 1)
        self.assertGreaterEqual(len(loop[0]), 4)

    def test_contours_trace_closed_shape(self):
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[4:16, 4:16] = 1
        found = contours(mask, minimum_area=1, simplify=1)
        self.assertEqual(len(found), 1)
        self.assertGreaterEqual(len(found[0]), 4)

    def test_multi_threshold_masks_are_nested(self):
        luminance = np.tile(np.arange(0, 256, 16, dtype=np.uint8), (8, 1))
        image = Image.fromarray(luminance, "L")
        masks = multi_threshold_masks(image, 3, False, False, 0)
        self.assertEqual(len(masks), 3)
        self.assertLessEqual(int(masks[0].sum()), int(masks[1].sum()))
        self.assertLessEqual(int(masks[1].sum()), int(masks[2].sum()))

    def test_live_preview_pipeline_supports_all_modes(self):
        pixels = np.full((32, 32, 4), (255, 255, 255, 255), dtype=np.uint8)
        pixels[12:20, 4:28] = (0, 0, 0, 255)
        image = Image.fromarray(pixels, "RGBA")
        for mode in ("Contours", "Multi-threshold", "Centerline", "Print then cut"):
            records = trace_image(
                image,
                mode=mode,
                remove_background=False,
                minimum_area=1,
                simplify=1,
            )
            self.assertTrue(records, mode)

    def test_zhang_suen_reduces_thick_stroke_to_centerline(self):
        mask = np.zeros((11, 15), dtype=np.uint8)
        mask[3:8, 2:13] = 1
        skeleton = zhang_suen(mask)
        self.assertLess(int(skeleton.sum()), int(mask.sum()))
        paths = skeleton_paths(skeleton)
        self.assertTrue(paths)
        self.assertGreaterEqual(max(len(path) for path in paths), 5)


if __name__ == "__main__":
    unittest.main()