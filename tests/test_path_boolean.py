import os
import sys
import unittest

BCNC = os.path.join(os.path.dirname(__file__), "..", "bCNC")
LIB = os.path.join(BCNC, "lib")
for path in (BCNC, LIB):
    if path not in sys.path:
        sys.path.insert(0, path)

from bmath import Vector
from bpath import Path, Segment
from path_boolean import boolean_paths


def rectangle(name, x1, y1, x2, y2):
    points = [
        Vector(x1, y1),
        Vector(x2, y1),
        Vector(x2, y2),
        Vector(x1, y2),
    ]
    path = Path(name)
    for index, point in enumerate(points):
        path.append(Segment(Segment.LINE, point, points[(index + 1) % 4]))
    return path


def contour_area(path):
    return abs(sum(
        segment.A[0] * segment.B[1] - segment.B[0] * segment.A[1]
        for segment in path
    )) / 2.0


class PathBooleanTest(unittest.TestCase):
    def setUp(self):
        self.a = rectangle("A", 0.0, 0.0, 2.0, 2.0)
        self.b = rectangle("B", 1.0, 1.0, 3.0, 3.0)

    def assert_result_area(self, operation, expected):
        paths = boolean_paths(self.a, self.b, operation)
        self.assertAlmostEqual(sum(map(contour_area, paths)), expected)

    def test_intersection(self):
        self.assert_result_area("intersection", 1.0)

    def test_union(self):
        self.assert_result_area("union", 7.0)

    def test_difference(self):
        self.assert_result_area("difference", 3.0)

    def test_symmetric_difference(self):
        self.assert_result_area("symmetric_difference", 6.0)

    def test_requires_closed_paths(self):
        open_path = Path("open")
        open_path.append(
            Segment(Segment.LINE, Vector(0.0, 0.0), Vector(1.0, 0.0))
        )
        with self.assertRaises(ValueError):
            boolean_paths(open_path, self.b, "union")

    def test_identical_paths(self):
        identical = rectangle("same", 0.0, 0.0, 2.0, 2.0)
        self.assertEqual(len(boolean_paths(self.a, identical, "intersection")), 1)
        self.assertEqual(len(boolean_paths(self.a, identical, "union")), 1)
        self.assertEqual(boolean_paths(self.a, identical, "difference"), [])
        self.assertEqual(
            boolean_paths(self.a, identical, "symmetric_difference"), []
        )

    def test_shared_edge(self):
        left = rectangle("left", 0.0, 0.0, 1.0, 1.0)
        right = rectangle("right", 1.0, 0.0, 2.0, 1.0)
        self.assertEqual(boolean_paths(left, right, "intersection"), [])
        union = boolean_paths(left, right, "union")
        self.assertEqual(len(union), 1)
        self.assertAlmostEqual(contour_area(union[0]), 2.0)
        difference = boolean_paths(left, right, "difference")
        self.assertAlmostEqual(sum(map(contour_area, difference)), 1.0)
        symmetric = boolean_paths(left, right, "symmetric_difference")
        self.assertAlmostEqual(sum(map(contour_area, symmetric)), 2.0)


if __name__ == "__main__":
    unittest.main()
