"""Versioned local projects and undoable document edits; no UI or serial access."""
from copy import deepcopy
from pathlib import Path
import json
import os
import tempfile
from CNC import Block
from PlotterEditing import IDENTITY, number, contour_points

FORMAT = 'foil-studio-project'
VERSION = 1


class ProjectBlocks(list):
    """Carry decoded layer records while preserving the existing read API."""
    layers = None


def metadata(block):
    return deepcopy(getattr(block, 'foil', {}))


def snapshot(document, mat):
    objects=[]
    for i, block in enumerate(document.blocks):
        objects.append({'name':block.name(),'enabled':bool(block.enable), 'color':block.color,
                        'passes':block.passes, 'lines':list(block), 'design':metadata(block),
                        'outlines':[contour_points(p) for p in document.toPath(i)]
                        if block.name() not in ('Header','Footer') else []})
    from PlotterLayers import catalog
    return {'format':FORMAT,'version':VERSION,'mat':list(mat),'objects':objects, 'layers':catalog(document)}


def decode(data):
    if not isinstance(data,dict) or data.get('format')!=FORMAT or type(data.get('version')) is not int or data.get('version')!=VERSION:
        raise ValueError('This project format is not supported. Open a Foil Studio version 1 project.')
    mat=data.get('mat')
    if not isinstance(mat,list) or len(mat)!=2: raise ValueError('The project has invalid mat dimensions.')
    mat=tuple(number(v,1,10000) for v in mat)
    objects=data.get('objects')
    if not isinstance(objects,list) or len(objects)>10000: raise ValueError('The project object list is invalid or too large.')
    blocks=ProjectBlocks()
    for obj in objects:
        if not isinstance(obj,dict) or not isinstance(obj.get('name'),str): raise ValueError('An object name is invalid.')
        lines=obj.get('lines'); design=obj.get('design',{})
        if type(obj.get('enabled',True)) is not bool: raise ValueError('An object visibility value is invalid.')
        outlines=obj.get('outlines',[])
        if not isinstance(outlines,list): raise ValueError('An object has invalid vector outlines.')
        for path in outlines:
            if not isinstance(path,list): raise ValueError('An object has invalid vector outlines.')
            for point in path:
                if not isinstance(point,list) or len(point)!=2: raise ValueError('A vector node is invalid.')
                for coordinate in point: number(coordinate)
        if not isinstance(lines,list) or any(not isinstance(s,str) or '\x00' in s or '\n' in s for s in lines):
            raise ValueError('An object contains invalid cut data.')
        if not isinstance(design,dict): raise ValueError('An object has invalid design properties.')
        for key in ('group','layer'):
            if key in design and (not isinstance(design[key],str) or len(design[key])>200):
                raise ValueError('An object has an invalid group or material layer.')
        if 'matrix' in design:
            if not isinstance(design['matrix'],list) or len(design['matrix'])!=6: raise ValueError('An object transform is invalid.')
            design['matrix']=[number(v) for v in design['matrix']]
        if 'text' in design:
            text=design['text']
            if not isinstance(text,dict) or not isinstance(text.get('text'),str) or len(text['text'])>1000:
                raise ValueError('A text object is invalid.')
            if not isinstance(text.get('font'),str): raise ValueError('A text font reference is invalid.')
            number(text.get('height'),.01,1000)
            number(text.get('letter_spacing',0),-100,100)
            number(text.get('line_spacing',1.2),.2,10)
            number(text.get('radius',0),0,10000)
            if text.get('alignment','Left') not in ('Left','Center','Right'): raise ValueError('Text alignment is invalid.')
        color=obj.get('color')
        if color is not None:
            import re
            if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color): color=None
        block=Block(obj['name']); block.extend(lines); block.foil=deepcopy(design)
        block.enable=bool(obj.get('enabled',True)); block.color=color
        passes=number(obj.get('passes',1),1,100)
        if int(passes)!=passes: raise ValueError('Cut passes must be a whole number.')
        block.passes=int(passes)
        blocks.append(block)
    for name in ('Header','Footer'):
        if sum(b.name()==name for b in blocks)>1: raise ValueError('The project has duplicate job headers or footers.')
    from PlotterLayers import validate_catalog, catalog, synchronize
    from types import SimpleNamespace
    if 'layers' in data:
        blocks.layers = validate_catalog(data['layers'])
    else:
        blocks.layers = catalog(SimpleNamespace(blocks=blocks, foil_layers=[]))
    synchronize(blocks, blocks.layers)
    return blocks, mat


def read(filename):
    path=Path(filename)
    if path.stat().st_size>25*1024*1024: raise ValueError('This project exceeds the 25 MB size limit.')
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        return decode(data)
    except (json.JSONDecodeError,UnicodeError,TypeError,KeyError) as error:
        raise ValueError('This project is damaged or incomplete. Try a recovery copy.') from error


def write(filename, data):
    """Validate first, then atomically replace; a failed write preserves the old file."""
    decode(deepcopy(data))
    content=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    if len(content.encode('utf-8'))>25*1024*1024: raise ValueError('This project exceeds the 25 MB size limit.')
    path=Path(filename)
    fd,temp=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def replace_blocks(document, blocks):
    previous=document.blocks
    document.blocks=blocks
    return replace_blocks,document,previous


def commit(document, blocks, title):
    document.addUndo(replace_blocks(document,blocks),title)


def changed_block(document, source, paths, matrix=None, preserve_text=False):
    block=document.fromPath(paths,z=0) if paths else Block(source.name())
    block._name=source.name(); block.enable=source.enable; block.color=source.color; block.passes=source.passes
    block.foil=metadata(source)
    block.foil['vector']=True
    if not preserve_text:
        block.foil.pop('text',None)
        block.foil['matrix']=list(IDENTITY)
        block.foil['source_outlines']=[contour_points(path) for path in paths]
        block.foil['rendered']=list(block)
    elif matrix is not None and ('text' not in block.foil or block.foil.get('rendered')==list(source)):
        from PlotterEditing import multiply
        block.foil['matrix']=multiply(matrix,block.foil.get('matrix',IDENTITY))
    if 'text' in block.foil and block.foil.get('rendered')==list(source): block.foil['rendered']=list(block)
    return block


def set_properties(document, index, properties):
    old=metadata(document.blocks[index]); document.blocks[index].foil=deepcopy(properties)
    return set_properties,document,index,old


def command_matrix(command, args):
    import math
    if command=='MOVE': return [1,0,0,1,args[0] if args else 0,args[1] if len(args)>1 else 0]
    if command=='MIRRORH': return [-1,0,0,1,0,0]
    if command=='MIRRORV': return [1,0,0,-1,0,0]
    if command=='SCALE':
        x=args[0]; y=args[1] if len(args)>1 and args[1] is not None else x
        cx=args[2] if len(args)>2 else 0; cy=args[3] if len(args)>3 else 0
        return [x,0,0,y,cx*(1-x),cy*(1-y)]
    if command=='ROTATE':
        angle=args[0]; cx=args[1] if len(args)>1 else 0; cy=args[2] if len(args)>2 else 0
        c=math.cos(math.radians(angle)); s=math.sin(math.radians(angle))
        return [c,s,-s,c,cx-c*cx+s*cy,cy-s*cx-c*cy]
    return None
