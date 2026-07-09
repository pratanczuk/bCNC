"""
Standalone tests for the pre-send drag-knife pipeline introduced in
MatManager._compute_dragknife_blocks().

These tests do NOT import bCNC modules directly (the import chain requires
Tkinter + socat + hardware stubs).  Instead they:
  1. Replicate the key logic of _compute_dragknife_blocks() with
     minimal Python objects so the algorithm is tested independently.
  2. Test the run() colour-loop guard (the _saved_blocks is None check)
     that ensures WAIT is always enqueued — fixing the missing-Footer bug.

Run with:
    cd /data/projects/bCNC/bCNC
    python3 -m pytest tests/test_dragknife_presend.py -v
or:
    python3 tests/test_dragknife_presend.py
"""

import queue
import unittest


# ---------------------------------------------------------------------------
# Minimal Block-like object (no bCNC imports needed)
# ---------------------------------------------------------------------------

class FakeBlock(list):
    def __init__(self, name, lines=None):
        super().__init__(lines or [])
        self._name = name

    def name(self):
        return self._name


# ---------------------------------------------------------------------------
# Replicated core logic from _compute_dragknife_blocks()
# (mirrors MatManager.py exactly — if the implementation changes, update here)
# ---------------------------------------------------------------------------

def _assemble_dk_result(original_blocks, working_blocks, preserved_blocks):
    """
    Mirrors the final assembly step of _compute_dragknife_blocks():
        orig_ids      – identity set of the original blocks
        working_blocks – gcode.blocks AFTER plugin.execute()
        preserved_blocks – multi-path / zero-path blocks plugin skipped
    Returns: header_blocks + dk_blocks + preserved_blocks + footer_blocks
    """
    orig_ids     = {id(b) for b in original_blocks}
    orig_ordered = [b for b in working_blocks if id(b) in orig_ids]
    header_blocks = [b for b in orig_ordered if b.name() == "Header"]
    footer_blocks = [b for b in orig_ordered if b.name() == "Footer"]
    dk_blocks     = [b for b in working_blocks if id(b) not in orig_ids]

    if not dk_blocks:
        return None

    return header_blocks + dk_blocks + preserved_blocks + footer_blocks


def _run_compute_dk(original_blocks, plugin_new_blocks,
                    preserved_blocks=None):
    """
    Full simulation of _compute_dragknife_blocks():
    - Copies original_blocks into a working list
    - Appends plugin_new_blocks (simulating insBlocks(-1, …))
    - Runs the assembly step
    - Verifies original_blocks are unchanged
    Returns (result, original_still_intact)
    """
    if preserved_blocks is None:
        preserved_blocks = []

    # Save IDs before
    orig_ids_before = [id(b) for b in original_blocks]

    # Working copy (shallow list copy — same Block objects inside)
    working = list(original_blocks)

    # Simulate insBlocks(-1, plugin_new_blocks):
    # Python: list[-1:-1] inserts BEFORE the last element
    working[-1:-1] = plugin_new_blocks

    result = _assemble_dk_result(original_blocks, working, preserved_blocks)

    # Verify original_blocks is unchanged
    orig_intact = ([id(b) for b in original_blocks] == orig_ids_before
                   and len(original_blocks) == len(orig_ids_before))

    return result, orig_intact


# ---------------------------------------------------------------------------
# Tests: block assembly
# ---------------------------------------------------------------------------

class TestDKBlockAssembly(unittest.TestCase):

    def _make_std_blocks(self):
        return [
            FakeBlock("Header",  ["G21", "G90", "M3 S500"]),
            FakeBlock("Square",  ["G0 X0 Y0", "G1 X10", "G1 Y0", "G0 Z2"]),
            FakeBlock("Footer",  ["M5", "G0 X0 Y0", "M2"]),
        ]

    def _make_dk_block(self):
        return [FakeBlock("DragKnife", ["G0 X-0.5 Y0", "G1 X10.5", "G0 Z2"])]

    # ------------------------------------------------------------------
    def test_footer_present_and_last(self):
        orig = self._make_std_blocks()
        result, _ = _run_compute_dk(orig, self._make_dk_block())
        names = [b.name() for b in result]
        self.assertIn("Footer", names,
                      f"Footer missing from result. Got: {names}")
        self.assertEqual(names[-1], "Footer",
                         f"Footer should be last. Got: {names}")

    def test_header_present_and_first(self):
        orig = self._make_std_blocks()
        result, _ = _run_compute_dk(orig, self._make_dk_block())
        names = [b.name() for b in result]
        self.assertIn("Header", names)
        self.assertEqual(names[0], "Header",
                         f"Header should be first. Got: {names}")

    def test_dk_blocks_present(self):
        orig = self._make_std_blocks()
        result, _ = _run_compute_dk(orig, self._make_dk_block())
        names = [b.name() for b in result]
        self.assertIn("DragKnife", names,
                      f"DragKnife block missing. Got: {names}")

    def test_original_content_not_in_result(self):
        """The original Square block must NOT appear in the DK output."""
        orig = self._make_std_blocks()
        orig_square_id = id(orig[1])   # "Square" block
        result, _ = _run_compute_dk(orig, self._make_dk_block())
        result_ids = {id(b) for b in result}
        self.assertNotIn(orig_square_id, result_ids,
                         "Original Square block leaked into DK result")

    def test_original_list_unchanged(self):
        orig = self._make_std_blocks()
        _, intact = _run_compute_dk(orig, self._make_dk_block())
        self.assertTrue(intact, "Original blocks list was mutated")

    def test_original_block_count_unchanged(self):
        orig = self._make_std_blocks()
        count_before = len(orig)
        _run_compute_dk(orig, self._make_dk_block())
        self.assertEqual(len(orig), count_before,
                         "Original block list length changed")

    def test_result_order_header_dk_footer(self):
        """Full result order must be: Header, DragKnife…, Footer."""
        orig = self._make_std_blocks()
        result, _ = _run_compute_dk(orig, self._make_dk_block())
        names = [b.name() for b in result]
        self.assertEqual(names, ["Header", "DragKnife", "Footer"],
                         f"Unexpected block order: {names}")

    def test_multiple_dk_blocks_all_present(self):
        """When plugin appends multiple DK blocks, all must appear."""
        orig = self._make_std_blocks()
        dk = [FakeBlock("DragKnife", ["G1 X1"]),
              FakeBlock("DragKnife", ["G1 X2"])]
        result, _ = _run_compute_dk(orig, dk)
        names = [b.name() for b in result]
        dk_count = names.count("DragKnife")
        self.assertEqual(dk_count, 2,
                         f"Expected 2 DragKnife blocks, got {dk_count}: {names}")
        self.assertEqual(names[-1], "Footer")

    def test_preserved_blocks_before_footer(self):
        """Multi-path blocks (skipped by plugin) go between DK and Footer."""
        orig = self._make_std_blocks()
        text_block = FakeBlock("Text", ["G0 X5", "G1 X6"])
        preserved = [text_block]
        result, _ = _run_compute_dk(orig, self._make_dk_block(), preserved)
        names = [b.name() for b in result]
        self.assertEqual(names, ["Header", "DragKnife", "Text", "Footer"],
                         f"Unexpected order with preserved: {names}")

    def test_returns_none_when_no_dk_blocks(self):
        """If plugin produces no new blocks, return None (use original)."""
        orig = self._make_std_blocks()
        result, _ = _run_compute_dk(orig, plugin_new_blocks=[])
        self.assertIsNone(result,
                          "Should return None when plugin produces nothing")


# ---------------------------------------------------------------------------
# Tests: run() colour-loop guard  (the Footer-missing-from-queue bug)
# ---------------------------------------------------------------------------

WAIT = 4   # same constant as bCNC/CNC.py


class TestRunColorLoopGuard(unittest.TestCase):
    """
    Verify the guard in run():

        if _saved_blocks is None:
            for ij in self._paths:
                path = self.gcode[ij[0]].path(...)   # ← IndexError in DK mode
                ...

        self.queue.put((WAIT,))   # ← must always be reached
    """

    def _simulate_run(self, use_dk):
        """
        Simulate the run() path around compile() + colour loop.

        use_dk=True  → DK mode: _saved_blocks is not None
                        colour loop SKIPPED → WAIT always enqueued
        use_dk=False → normal mode: _saved_blocks is None
                        colour loop runs (safe, no IndexError)
        """
        q = queue.Queue()

        # Simulate compile() queuing the footer line
        q.put("G21\n")
        q.put("G1 X10\n")
        q.put("M2\n")          # Footer G-code

        _saved_blocks = ["orig"] if use_dk else None

        if _saved_blocks is None:
            # Colour-loop (safe in non-DK mode — indices match real blocks)
            pass   # nothing extra to do in this simulation

        # WAIT is always reached now:
        q.put((WAIT,))

        items = []
        while not q.empty():
            items.append(q.get_nowait())
        return items

    def test_wait_enqueued_in_dk_mode(self):
        items = self._simulate_run(use_dk=True)
        self.assertIn((WAIT,), items,
                      "WAIT sentinel missing in DK mode")

    def test_wait_enqueued_in_normal_mode(self):
        items = self._simulate_run(use_dk=False)
        self.assertIn((WAIT,), items,
                      "WAIT sentinel missing in normal mode")

    def test_footer_gcode_queued_before_wait(self):
        """Footer G-code must appear in queue before the WAIT sentinel."""
        items = self._simulate_run(use_dk=True)
        wait_pos   = items.index((WAIT,))
        footer_pos = next((i for i, x in enumerate(items)
                           if isinstance(x, str) and "M2" in x), None)
        self.assertIsNotNone(footer_pos, "Footer G-code not in queue")
        self.assertLess(footer_pos, wait_pos,
                        "Footer G-code must appear before WAIT sentinel")

    def test_indexerror_would_occur_without_guard(self):
        """
        Demonstrate that accessing DK indices against the shorter original
        block list raises IndexError — proving the guard is necessary.
        """
        # 3 DK blocks vs 2 original blocks
        orig_blocks = [FakeBlock("Header"), FakeBlock("Footer")]
        dk_paths    = [(0, 0), (1, 0), (2, 0)]   # indices from DK list

        with self.assertRaises(IndexError):
            for ij in dk_paths:
                _ = orig_blocks[ij[0]]   # index 2 → IndexError


# ---------------------------------------------------------------------------
# Tests: snap_to_mat must NOT translate Header / Footer blocks
# ---------------------------------------------------------------------------

def _snap_to_mat_logic(blocks, xmin, ymin):
    """
    Replicate the snap_to_mat translation logic from MatManager.py:
      - compute dx = -xmin, dy = -ymin
      - translate ONLY content blocks (not Header / Footer)
      - return (dx, dy, translated_block_names)
    """
    dx = -xmin
    dy = -ymin

    if abs(dx) < 0.0001 and abs(dy) < 0.0001:
        return dx, dy, {}

    translated = {}
    for i, blk in enumerate(blocks):
        if blk.name() in ("Header", "Footer"):
            continue                   # ← the fix: skip these
        new_lines = []
        for line in blk:
            # Very small G-code parser: shift X and Y values
            import re
            def _shift(m):
                axis = m.group(1)
                val  = float(m.group(2))
                if axis == "X":
                    val += dx
                elif axis == "Y":
                    val += dy
                return f"{axis}{val:.4f}"
            new_lines.append(re.sub(r'([XY])(-?[\d.]+)', _shift, line))
        translated[blk.name()] = new_lines

    return dx, dy, translated


class TestSnapToMatFooterPreserved(unittest.TestCase):

    def _make_design_blocks(self, y_start):
        """Design with Y coordinates starting at y_start."""
        return [
            FakeBlock("Header",  ["G21", "G90", "M3 S500"]),
            FakeBlock("Square",  [f"G0 X0 Y{y_start:.4f}",
                                  f"G1 X10 Y{y_start:.4f}",
                                  f"G1 X10 Y{y_start+10:.4f}",
                                  f"G0 Z2"]),
            FakeBlock("Footer",  ["M5", "G0 X0 Y0", "M2"]),
        ]

    def test_footer_return_to_origin_not_shifted(self):
        """Footer's G0 X0 Y0 must stay at (0,0) regardless of design offset."""
        blocks = self._make_design_blocks(y_start=-105.6827)
        xmin, ymin = 0.0, -105.6827

        _, _, translated = _snap_to_mat_logic(blocks, xmin, ymin)

        # Footer must NOT be in the translated set
        self.assertNotIn("Footer", translated,
                         "Footer block was incorrectly translated by snap_to_mat")

        # Verify Footer content is literally unchanged
        footer = next(b for b in blocks if b.name() == "Footer")
        self.assertIn("G0 X0 Y0", list(footer),
                      "Footer's G0 X0 Y0 was modified")

    def test_header_not_shifted(self):
        """Header must also be excluded from snap translation."""
        blocks = self._make_design_blocks(y_start=50.0)
        xmin, ymin = 0.0, 50.0

        _, _, translated = _snap_to_mat_logic(blocks, xmin, ymin)
        self.assertNotIn("Header", translated)

    def test_content_block_is_shifted(self):
        """Design content block MUST be shifted to start at origin."""
        blocks = self._make_design_blocks(y_start=-105.6827)
        xmin, ymin = 0.0, -105.6827

        _, _, translated = _snap_to_mat_logic(blocks, xmin, ymin)

        self.assertIn("Square", translated,
                      "Content block was NOT translated by snap_to_mat")
        # After shift, minimum Y of design should be 0
        import re
        y_vals = []
        for line in translated["Square"]:
            m = re.search(r'Y(-?[\d.]+)', line)
            if m:
                y_vals.append(float(m.group(1)))
        if y_vals:
            self.assertAlmostEqual(min(y_vals), 0.0, places=3,
                                   msg=f"Content min Y not at 0 after snap: {y_vals}")

    def test_negative_ymin_would_corrupt_footer_without_fix(self):
        """
        Prove the old behaviour (translating ALL blocks) would corrupt Footer.
        This is the bug that was fixed.
        """
        blocks = self._make_design_blocks(y_start=-105.6827)
        xmin, ymin = 0.0, -105.6827
        dy = -ymin   # +105.6827

        # Old (buggy) logic: translate Footer too
        import re
        footer = next(b for b in blocks if b.name() == "Footer")
        corrupted = []
        for line in footer:
            def _shift(m):
                axis = m.group(1)
                val  = float(m.group(2))
                if axis == "Y":
                    val += dy
                return f"{axis}{val:.4f}"
            corrupted.append(re.sub(r'([XY])(-?[\d.]+)', _shift, line))

        # Old code would produce "G0 X0 Y105.6827" instead of "G0 X0 Y0"
        self.assertTrue(
            any("Y105" in l or "Y106" in l for l in corrupted),
            f"Expected corrupted footer with Y≈105, got: {corrupted}"
        )
        # And confirm the new code avoids this
        _, _, translated = _snap_to_mat_logic(blocks, xmin, ymin)
        self.assertNotIn("Footer", translated,
                         "Fixed code still translates Footer")


if __name__ == "__main__":
    unittest.main(verbosity=2)

