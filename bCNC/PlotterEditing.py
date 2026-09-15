"""Explicit-input vector editing, layout and cut-order planning (no Tk)."""
from copy import deepcopy
import math
from bmath import Vector
from bpath import Path, Segment
from PlotterGeometry import outlines_geometry, geometry_paths

IDENTITY = [1, 0, 0, 1, 0, 0]


def number(value, minimum=-100000, maximum=100000):
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError('Enter a valid number.') from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'Enter a number from {minimum:g} to {maximum:g}.')
    return value


def bounds(paths):
    boxes = [p.bbox() for p in paths if p]
    if not boxes:
        raise ValueError('Select artwork with outlines first.')
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def multiply(a, b):
    return [a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5]]


def transform(paths, matrix):
    def point(p):
        a,b,c,d,e,f = matrix
        return Vector(a*p[0]+c*p[1]+e, b*p[0]+d*p[1]+f)
    result = []
    for source in paths:
        path = Path(source.name)
        for seg in source.linearize(.02):
            path.append(Segment(Segment.LINE, point(seg.A), point(seg.B)))
        result.append(path)
    return result


def translate(paths, x, y):
    return transform(paths, [1,0,0,1,x,y])


def fit(groups, width, height):
    box = bounds([p for g in groups for p in g])
    if box[0] < -.001 or box[1] < -.001 or box[2] > width+.001 or box[3] > height+.001:
        raise ValueError('This layout extends outside the mat. Reduce copies or spacing, or move the artwork inward.')


def layout(groups, operation, width, height, *, target='Selection', rows=1, columns=2, gap=5, margin=10):
    """Return (source index, affine matrix) placements; attached groups are units."""
    if not groups:
        raise ValueError('Select objects to arrange first.')
    boxes = [bounds(g) for g in groups]
    allbox = bounds([p for g in groups for p in g])
    result = []
    if operation == 'Repeat grid':
        r, c = number(rows,1,100), number(columns,1,100)
        if int(r)!=r or int(c)!=c or r*c*len(groups)>500:
            raise ValueError('Use whole rows and columns, with at most 500 resulting objects.')
        gap = number(gap,0,1000)
        for row in range(int(r)):
            for column in range(int(c)):
                result.extend((i,[1,0,0,1,column*(allbox[2]-allbox[0]+gap),row*(allbox[3]-allbox[1]+gap)]) for i in range(len(groups)))
    elif operation == 'Pack on mat':
        margin, gap = number(margin,0,1000), number(gap,0,1000)
        x=y=margin; shelf=0
        # Stable height-first shelf packing. No rotation and no claimed optimality.
        for i in sorted(range(len(groups)), key=lambda i: (-(boxes[i][3]-boxes[i][1]), i)):
            b=boxes[i]; w,h=b[2]-b[0],b[3]-b[1]
            if w>width-2*margin or h>height-2*margin:
                raise ValueError('An object is larger than the usable mat area.')
            if x+w>width-margin+.001:
                x=margin; y+=shelf+gap; shelf=0
            if y+h>height-margin+.001:
                raise ValueError('These objects do not fit with this margin and spacing.')
            result.append((i,[1,0,0,1,x-b[0],y-b[1]]))
            x+=w+gap; shelf=max(shelf,h)
    elif operation.startswith('Distribute'):
        if len(groups)<3:
            raise ValueError('Select at least three independent objects or groups to distribute.')
        axis=0 if operation.endswith('horizontal') else 1
        order=sorted(range(len(groups)),key=lambda i:boxes[i][axis])
        span=boxes[order[-1]][axis+2]-boxes[order[0]][axis]
        gap=(span-sum(b[axis+2]-b[axis] for b in boxes))/(len(groups)-1)
        if gap<0:
            raise ValueError('There is not enough space for equal gaps. Spread the outer objects farther apart.')
        cursor=boxes[order[0]][axis]
        for i in order:
            delta=cursor-boxes[i][axis]
            result.append((i,[1,0,0,1,delta if axis==0 else 0,delta if axis==1 else 0]))
            cursor+=boxes[i][axis+2]-boxes[i][axis]+gap
    else:
        box=(0,0,width,height) if target=='Mat' else allbox
        for i,b in enumerate(boxes):
            dx=dy=0
            if operation=='Align left': dx=box[0]-b[0]
            elif operation=='Align right': dx=box[2]-b[2]
            elif operation=='Align bottom': dy=box[1]-b[1]
            elif operation=='Align top': dy=box[3]-b[3]
            elif operation=='Center horizontally': dx=(box[0]+box[2]-b[0]-b[2])/2
            elif operation=='Center vertically': dy=(box[1]+box[3]-b[1]-b[3])/2
            else: raise ValueError('Choose a layout operation.')
            result.append((i,[1,0,0,1,dx,dy]))
    fit([transform(groups[i], matrix) for i,matrix in result],width,height)
    return result


def contour_points(path):
    linear=path.linearize(.02)
    return [list(seg.A[:2]) for seg in linear]+[list(linear[-1].B[:2])] if linear else []


def points_path(points, name='Edited contour'):
    path=Path(name)
    for a,b in zip(points,points[1:]):
        if a!=b: path.append(Segment(Segment.LINE,Vector(*a),Vector(*b)))
    return path


def repair(paths, operation, selected, tolerance=.1, node=0, x=0, y=0):
    if not 0<=selected<len(paths): raise ValueError('Choose a contour first.')
    result=deepcopy(paths); path=result[selected]
    if operation=='Hide contour':
        del result[selected]
    elif operation=='Close gap':
        tolerance=number(tolerance,.001,10)
        if not path.isClosed():
            distance=(path[-1].B-path[0].A).length()
            if distance>tolerance: raise ValueError('This gap exceeds the allowed distance. Increase the limit after inspecting it.')
            path.append(Segment(Segment.LINE,path[-1].B,path[0].A))
    elif operation=='Simplify':
        from shapely.geometry import LineString
        tolerance=number(tolerance,.001,5)
        line=LineString(contour_points(path)); simplified=line.simplify(tolerance,preserve_topology=True)
        if line.hausdorff_distance(simplified)>tolerance+1e-8: raise ValueError('Simplification would exceed the allowed deviation.')
        result[selected]=points_path(list(simplified.coords))
    elif operation in ('Move node','Insert node','Delete node'):
        points=contour_points(path); index=number(node,0,len(points)-1)
        if int(index)!=index: raise ValueError('Choose a whole node number.')
        index=int(index); closed=path.isClosed()
        if operation=='Move node':
            points[index]=[number(x),number(y)]
            if closed and index in (0,len(points)-1): points[0]=points[-1]=points[index]
        elif operation=='Insert node':
            points.insert(index+1,[number(x),number(y)])
            if closed and index==len(points)-2:
                points[-1],points[-2]=points[-2],points[-1]
        else:
            if closed:
                points=points[:-1]
                if index==len(points): index=0
                if len(points)<=3: raise ValueError('A closed contour needs at least three nodes.')
                del points[index]; points.append(points[0])
            else:
                if len(points)<=2: raise ValueError('An open contour needs at least two nodes.')
                del points[index]
        result[selected]=points_path(points)
    else: raise ValueError('Choose a contour operation.')
    if operation!='Hide contour' and path.isClosed():
        from shapely.geometry import Polygon
        if not Polygon(contour_points(result[selected])).is_valid:
            raise ValueError('That edit crosses the contour. Move the node to another position.')
    return result


def weed_lines(groups, spacing=20, clearance=1, margin=3):
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    spacing,clearance,margin=number(spacing,1,1000),number(clearance,.05,100),number(margin,.1,100)
    artwork=unary_union([outlines_geometry(g) for g in groups])
    if artwork.is_empty: raise ValueError('Select closed artwork first.')
    x0,y0,x1,y1=artwork.bounds
    protected=artwork.buffer(clearance)
    # Protect holes too: weed cuts never enter an object's outer contour.
    polygons=list(artwork.geoms) if artwork.geom_type=='MultiPolygon' else [artwork]
    from shapely.geometry import Polygon
    protected=unary_union([Polygon(p.exterior).buffer(clearance) for p in polygons])
    border=box(x0-margin,y0-margin,x1+margin,y1+margin)
    if border.boundary.intersects(protected):
        raise ValueError('Use a border margin larger than the clearance.')
    result=geometry_paths(border)
    count=int((y1-y0+2*margin)/spacing)
    if count>1000: raise ValueError('Increase spacing to use fewer than 1000 weeding lines.')
    for row in range(1,count+1):
        y=y0-margin+row*spacing
        if y>=y1+margin: break
        remaining=LineString([(x0-margin,y),(x1+margin,y)]).difference(protected)
        lines=list(remaining.geoms) if hasattr(remaining,'geoms') else [remaining]
        for line in lines:
            if line.geom_type=='LineString' and line.length>.05:
                if line.intersects(artwork): raise ValueError('A weed cut would cross artwork; increase clearance.')
                result.append(points_path(list(line.coords),'Weeding line'))
    return result


def cut_order(paths):
    """Stable inner-before-outer ordering; open paths keep their input rank."""
    from shapely.geometry import Polygon
    polygons=[Polygon(contour_points(p)) if p.isClosed() else None for p in paths]
    for polygon in polygons:
        if polygon is not None and not polygon.is_valid:
            raise ValueError('Repair crossing contours before ordering cuts.')
    depths=[sum(other is not None and other.contains(poly) for j,other in enumerate(polygons) if j!=i)
            if poly is not None else 0 for i,poly in enumerate(polygons)]
    return sorted(range(len(paths)),key=lambda i:(-depths[i],i))


def order_blocks(blocks):
    """Order vector artwork on a separate document; preserve job wrappers and passes.

    Arbitrary imported G-code may contain modal/tool actions between contours and
    must not be rewritten as geometry. It is explicitly rejected for this option.
    """
    from CNC import GCode
    from PlotterProject import changed_block
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    job=GCode(); job.blocks=deepcopy(blocks)
    ids=[]; footprints=[]; ordered=[]
    for i,b in enumerate(job.blocks):
        if not b.enable or b.name() in ('Header','Footer'): continue
        paths=job.toPath(i)
        if not paths: continue
        if not getattr(b,'foil',{}).get('vector'):
            raise ValueError('Inner-first ordering needs vector artwork. Turn it off for imported machine G-code.')
        order=cut_order(paths)
        new=changed_block(job,b,[paths[j] for j in order],preserve_text=True)
        ids.append(i); ordered.append(new)
        footprints.append(unary_union([Polygon(contour_points(p)) for p in paths if p.isClosed()]))
    depths=[sum(not other.is_empty and other.contains(shape) and not other.equals(shape)
                for j,other in enumerate(footprints) if i!=j) if not shape.is_empty else 0
            for i,shape in enumerate(footprints)]
    for slot,index in zip(ids,sorted(range(len(ids)),key=lambda i:(-depths[i],i))):
        job.blocks[slot]=ordered[index]
    return job.blocks
