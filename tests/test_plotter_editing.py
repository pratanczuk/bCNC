"""Priority 1/2 feature contracts independent of a display or serial connection."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
for directory in ('bCNC','bCNC/lib'): sys.path.insert(0,str(ROOT/directory))
import Helpers
from CNC import CNC, Block, GCode
from shapely.geometry import box, LineString, Polygon
from PlotterGeometry import geometry_paths, outlines_geometry
from PlotterEditing import layout, transform, bounds, repair, weed_lines, cut_order, contour_points, order_blocks
import PlotterProject as project


def rectangle(x=10,y=10,w=10,h=10): return geometry_paths(box(x,y,x+w,y+h))


class LayoutTest(unittest.TestCase):
    def test_align_to_mat_and_repeat_keep_input_unchanged(self):
        groups=[rectangle(),rectangle(40,20)]
        before=[bounds(g) for g in groups]
        placements=layout(groups,'Align right',100,100,target='Mat')
        for i,m in placements: self.assertAlmostEqual(bounds(transform(groups[i],m))[2],100,places=4)
        repeats=layout(groups,'Repeat grid',200,200,rows=2,columns=2,gap=5)
        self.assertEqual(len(repeats),8)
        self.assertEqual([bounds(g) for g in groups],before)

    def test_distribute_equal_edge_gaps_with_different_sizes(self):
        groups=[rectangle(10,10,10,10),rectangle(24,10,20,10),rectangle(80,10,5,10)]
        result=[bounds(transform(groups[i],m)) for i,m in layout(groups,'Distribute horizontal',100,100)]
        self.assertAlmostEqual(result[1][0]-result[0][2],result[2][0]-result[1][2])
        self.assertAlmostEqual(result[0][0],10,places=4)
        self.assertAlmostEqual(result[-1][2],85,places=4)

    def test_pack_is_deterministic_nonoverlapping_and_respects_margins(self):
        groups=[rectangle(10,10,20,30),rectangle(5,5,40,10),rectangle(20,10,20,20)]
        first=layout(groups,'Pack on mat',100,100,gap=3,margin=5)
        self.assertEqual(first,layout(groups,'Pack on mat',100,100,gap=3,margin=5))
        shapes=[outlines_geometry(transform(groups[i],m)) for i,m in first]
        for i,shape in enumerate(shapes):
            self.assertGreaterEqual(shape.bounds[0],4.999)
            for other in shapes[i+1:]: self.assertFalse(shape.intersects(other))

    def test_overflow_fractional_copies_and_negative_gap_rejected(self):
        for options in ({'columns':100},{'rows':1.5},{'gap':-1}):
            with self.assertRaises(ValueError): layout([rectangle()],'Repeat grid',50,50,**options)
        with self.assertRaises(ValueError): layout([rectangle(0,0,50,50)],'Pack on mat',40,40)


class ContourTest(unittest.TestCase):
    def test_hide_preserves_other_contours_and_source(self):
        paths=rectangle()+rectangle(30,30)
        result=repair(paths,'Hide contour',0)
        self.assertEqual(len(result),1); self.assertEqual(len(paths),2)
        self.assertEqual(bounds(result),bounds(paths[1:]))

    def test_close_gap_limit_and_simplification_deviation(self):
        from PlotterEditing import points_path
        path=points_path([(10,10),(20,10),(20,20),(10,20),(10,10.05)])
        with self.assertRaises(ValueError): repair([path],'Close gap',0,.01)
        self.assertTrue(repair([path],'Close gap',0,.1)[0].isClosed())
        source=points_path([(10,10),(15,10.01),(20,10),(20,20),(10,20),(10,10)])
        result=repair([source],'Simplify',0,.1)[0]
        self.assertLess(len(result),len(source))
        self.assertLessEqual(LineString(contour_points(source)).hausdorff_distance(LineString(contour_points(result))),.1)

    def test_move_closed_endpoint_keeps_ring_closed_and_rejects_crossing(self):
        paths=rectangle(); result=repair(paths,'Move node',0,node=0,x=21,y=9)
        self.assertTrue(result[0].isClosed())
        self.assertNotEqual(contour_points(result[0]),contour_points(paths[0]))
        with self.assertRaises(ValueError): repair(paths,'Move node',0,node=1,x=5,y=15)

    def test_node_insert_delete_preserve_closed_topology(self):
        paths=rectangle()
        inserted=repair(paths,'Insert node',0,node=0,x=21,y=15)
        self.assertTrue(inserted[0].isClosed())
        self.assertEqual(len(contour_points(inserted[0])),6)
        deleted=repair(inserted,'Delete node',0,node=1)
        self.assertEqual(contour_points(deleted[0]),contour_points(paths[0]))

    def test_weed_lines_never_enter_artwork_or_counters(self):
        groups=[rectangle(10,10,20,20)+rectangle(15,15,10,10),rectangle(40,10)]
        paths=weed_lines(groups,spacing=5,clearance=1,margin=3)
        protected=box(10,10,30,30).union(box(40,10,50,20))
        self.assertGreater(len(paths),1)
        for path in paths[1:]:
            line=LineString(contour_points(path))
            self.assertFalse(line.intersects(protected))
            self.assertGreaterEqual(line.distance(protected),.999)
        with self.assertRaises(ValueError): weed_lines(groups,margin=.5,clearance=1)

    def test_cut_order_inner_first_preserves_original(self):
        paths=rectangle(5,5,50,50)+rectangle(10,10,10,10)+rectangle(70,70)
        self.assertEqual(cut_order(paths),[1,0,2])
        self.assertEqual(len(paths),3)


class ProjectTest(unittest.TestCase):
    def job(self):
        job=GCode(); job.header='G90\nG21'; job.footer='M5'; job.headerFooter()
        b=job.fromPath(rectangle(),z=0); b._name='Lettering'
        b.foil={'vector':True,'group':'attached','layer':'Blue','matrix':[1,0,0,1,10,10],
                'text':{'text':'Zażółć','font':'/missing/font.ttf','height':10},'rendered':list(b)}
        b.enable=False; b.passes=2; b.color='#345bb1'; job.blocks.insert(1,b)
        return job

    def test_project_roundtrip_preserves_semantics_and_vector_outlines(self):
        job=self.job(); data=project.snapshot(job,(225,300))
        self.assertTrue(data['objects'][1]['outlines'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'unicode.foil'; project.write(path,data); blocks,mat=project.read(path)
        self.assertEqual(mat,(225,300)); self.assertEqual(blocks[1].foil,job.blocks[1].foil)
        self.assertFalse(blocks[1].enable); self.assertEqual(blocks[1].passes,2)
        self.assertEqual(list(blocks[1]),list(job.blocks[1]))

    def test_atomic_write_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'project.foil'; path.write_text('original')
            with patch('PlotterProject.os.replace',side_effect=OSError('disk full')):
                with self.assertRaises(OSError): project.write(path,project.snapshot(self.job(),(225,300)))
            self.assertEqual(path.read_text(),'original')
            self.assertEqual(list(Path(folder).iterdir()),[path])

    def test_invalid_version_transform_and_code_rejected(self):
        from copy import deepcopy
        data=project.snapshot(self.job(),(225,300))
        cases=[]
        bad=deepcopy(data); bad['version']=99; cases.append(bad)
        bad=deepcopy(data); bad['objects'][1]['design']['matrix']=[1]; cases.append(bad)
        bad=deepcopy(data); bad['objects'][1]['lines']=[{}]; cases.append(bad)
        for bad in cases:
            with self.assertRaises(ValueError): project.decode(bad)

    def test_full_document_undo_redo_restores_properties(self):
        from copy import deepcopy
        job=self.job(); before=project.snapshot(job,(225,300)); blocks=deepcopy(job.blocks)
        blocks[1].foil['layer']='Red'; blocks[1].enable=True
        project.commit(job,blocks,'Layer change'); job.undo()
        self.assertEqual(project.snapshot(job,(225,300)),before)
        job.redo(); self.assertTrue(job.blocks[1].enable); self.assertEqual(job.blocks[1].foil['layer'],'Red')

    def test_order_planning_is_separate_and_preserves_passes(self):
        job=GCode(); outer=job.fromPath(rectangle(5,5,60,60),z=0); outer._name='Outer'
        inner=job.fromPath(rectangle(10,10),z=0); inner._name='Inner'; inner.passes=3
        job.blocks=[outer,inner]
        result=order_blocks(job.blocks)
        self.assertEqual([b.name() for b in result],['Inner','Outer'])
        self.assertEqual(result[0].passes,3); self.assertEqual(job.blocks,[outer,inner])
        self.assertIsNot(result[1],outer)
        outer.foil={}
        with self.assertRaises(ValueError): order_blocks(job.blocks)


class TextLayoutTest(unittest.TestCase):
    def test_spacing_alignment_circle_and_unicode(self):
        from font_text import text_to_paths
        font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
        if not os.path.exists(font): self.skipTest('DejaVu font unavailable')
        plain=text_to_paths('AB',font,10)
        spaced=text_to_paths('AB',font,10,letter_spacing=3)
        self.assertGreater(bounds(spaced)[2]-bounds(spaced)[0],bounds(plain)[2]-bounds(plain)[0]+2.9)
        self.assertTrue(text_to_paths('Zażółć',font,10))
        circle=text_to_paths('OO',font,10,radius=30)
        self.assertGreaterEqual(len(circle),4)  # glyph counters survive rigid rotation
        with self.assertRaises(ValueError): text_to_paths('A\nB',font,10,radius=30)
        with self.assertRaises(ValueError): text_to_paths('AAAAAA',font,10,radius=1)
