"""Document selection and editing commands; no hidden Tk listbox or row indices."""
from copy import deepcopy
import json
from CNC import CNC, Block
from path_boolean import boolean_paths
from PlotterLayers import LayerManager, layer_name


class DocumentEditor:
    def __init__(self, app):
        self.app, self.gcode = app, app.gcode
        self.selected = []
        self.filter = None

    def fill(self, event=None):
        self.selected = [(i, j) for i, j in self.selected if 0 <= i < len(self.gcode.blocks)
                         and (j is None or 0 <= j < len(self.gcode.blocks[i]))]

    def getSelection(self):
        self.fill()
        return self.selected[:]

    def getSelectedBlocks(self):
        return sorted({i for i, j in self.getSelection()})


    def getActive(self):
        return next(iter(self.getSelection()), (0, None))

    def activeBlock(self):
        return self.getActive()[0]

    def select(self, items, double=False, clear=False, toggle=True):
        selected = set() if clear else set(self.getSelection())
        for i, j in items:
            if not 0 <= i < len(self.gcode.blocks): continue
            if not self.gcode.blocks[i].expand: j = None
            choices = [(i, j)]
            if double:
                choices = [(k, None) for k, b in enumerate(self.gcode.blocks)
                           if b.nameNop() == self.gcode.blocks[i].nameNop()]
            for item in choices:
                if toggle and not clear and item in selected: selected.remove(item)
                else: selected.add(item)
        self.selected = sorted(selected, key=lambda p: (p[0], -1 if p[1] is None else p[1]))
        self.fill()

    def selectBlocks(self, blocks):
        self.select([(i, None) for i in blocks], clear=True)

    def selectAll(self):
        self.selectBlocks([i for i, b in enumerate(self.gcode.blocks) if b.name() not in ('Header','Footer')])

    def selectClear(self):
        self.selected.clear()

    def selectInvert(self):
        current = self.getSelectedBlocks()
        self.selectBlocks([i for i,b in enumerate(self.gcode.blocks) if i not in current and b.name() not in ('Header','Footer')])

    def selectLayer(self):
        layers = {layer_name(self.gcode.blocks[i]) for i in self.getSelectedBlocks()}
        self.selectBlocks([i for i,b in enumerate(self.gcode.blocks) if b.name() not in ('Header','Footer') and layer_name(b) in layers])

    def changed(self):
        self.app.refresh()
        self.app.selectionChange()
        if hasattr(self.app, 'workflow'): self.app.workflow.confirmed.set(False)

    def manager_action(self, method, *args, **kwargs):
        try:
            manager = LayerManager(self.gcode, lambda: self.app.sender.running)
            result = getattr(manager, method)(self.getSelectedBlocks(), *args, **kwargs)
            self.selectBlocks(result if isinstance(result, list) else [])
            self.changed()
        except ValueError as error:
            self.app.reportPlotterError('Select artwork', str(error))
        return 'break'

    def clone(self, event=None): return self.manager_action('duplicate')
    def deleteBlock(self, event=None): return self.manager_action('delete_objects')
    def orderUp(self, event=None): return self.manager_action('order_objects', -1)
    def orderDown(self, event=None): return self.manager_action('order_objects', 1)
    def enable(self, event=None): return self.manager_action('object_properties', enabled=True)
    def disable(self, event=None): return self.manager_action('object_properties', enabled=False)
    def toggleEnable(self, event=None):
        ids = self.getSelectedBlocks()
        return self.manager_action('object_properties', enabled=not all(self.gcode.blocks[i].enable for i in ids))

    def toggleExpand(self, event=None):
        ids = self.getSelectedBlocks()
        self.gcode.addUndo([self.gcode.setBlockExpandUndo(i, not self.gcode.blocks[i].expand) for i in ids])
        self.selectBlocks(ids)

    def copy(self, event=None):
        blocks = [self.gcode.blocks[i] for i in self.getSelectedBlocks() if self.gcode.blocks[i].name() not in ('Header','Footer')]
        data = [{'name': b.name(), 'lines': list(b), 'foil': b.foil, 'enable': b.enable, 'color': b.color, 'passes': b.passes} for b in blocks]
        self.app.clipboard_clear(); self.app.clipboard_append(json.dumps({'foil_objects': data}))
        return 'break'

    def cut(self, event=None):
        self.copy(); return self.deleteBlock()

    def paste(self, event=None):
        if self.app.sender.running: return 'break'
        try:
            data = json.loads(self.app.clipboard_get())['foil_objects']
            import PlotterProject as project
            payload = project.snapshot(self.gcode, (225, 300))
            payload['objects'] = [{'name': o['name'], 'lines': o['lines'], 'design': o['foil'],
                                   'enabled': o['enable'], 'color': o['color'], 'passes': o['passes']} for o in data]
            payload.pop('layers', None)
            blocks, _ = project.decode(payload)
            import uuid
            groups = {}
            for b in blocks:
                if b.name() in ('Header','Footer'): raise ValueError('Select artwork objects.')
                group = b.foil.get('group')
                if group: b.foil['group'] = groups.setdefault(group, uuid.uuid4().hex)
            position = next((i for i,b in enumerate(self.gcode.blocks) if b.name()=='Footer'),len(self.gcode.blocks))
            self.gcode.addUndo(self.gcode.insBlocksUndo(position, blocks), 'Paste objects')
            self.selectBlocks(range(position, position+len(blocks))); self.changed()
        except (ValueError, TypeError, KeyError) as error:
            self.app.reportPlotterError('Could not paste artwork', 'Copy artwork in Foil Studio before pasting. '+str(error))
        return 'break'

    def edit(self, event=None): return self.app.workflow.design_dialog('LayersDialog')
    def changeColor(self, event=None): return self.edit()
    def insertItem(self, event=None): return self.app.workflow.add_shape()
    def insertBlock(self, event=None): return self.insertItem()
    def insertLine(self, event=None): return self.insertItem()
    def splitBlocks(self, event=None): return self.app.workflow.break_apart()
    def joinBlocks(self, event=None): return self.app.workflow.design_dialog('CombineDialog')
    def commentRow(self, event=None): return self.toggleEnable()

    def invertBlocks(self, event=None):
        ids = self.getSelectedBlocks()
        if ids:
            self.gcode.addUndo(self.gcode.invertBlocksUndo(ids)); self.changed()

    def smoothBlocks(self, tolerance=0.1, iterations=3, event=None):
        from smooth import smooth_path

        selected = self.getSelectedBlocks()
        if not selected:
            # fall back to every non-header/footer block
            selected = [
                bid
                for bid, block in enumerate(self.gcode.blocks)
                if block.name() not in ("Header", "Footer")
            ]
        if not selected:
            self.app.event_generate(
                "<<Status>>", data=_("No blocks to smooth")
            )
            return

        undoinfo = []
        count = 0
        for bid in reversed(selected):
            paths = self.gcode.toPath(bid)
            if not paths:
                continue
            smoothed = [smooth_path(p, tolerance, iterations) for p in paths]
            old = self.gcode.blocks[bid]
            new_block = self.gcode.fromPath(
                smoothed[0] if len(smoothed) == 1 else smoothed
            )
            new_block._name = old.name()
            new_block.color = old.color
            new_block.enable = old.enable
            new_block.passes = old.passes
            new_block.foil = deepcopy(old.foil)
            undoinfo.append(self.gcode.delBlockUndo(bid))
            undoinfo.append(self.gcode.addBlockUndo(bid, new_block))
            count += 1

        if undoinfo:
            self.gcode.addUndo(undoinfo, _("Smooth Path"))
            self.fill()
            self.app.event_generate("<<Modified>>")

        self.app.event_generate(
            "<<Status>>", data=_("Smoothed {:d} block(s)").format(count)
        )

    def _booleanPaths(self, operation, label):
        selected = self.getSelectedBlocks()
        if len(selected) != 2:
            self.app.event_generate(
                "<<Status>>", data=_("Select exactly two closed graphic blocks")
            )
            return

        paths_a = self.gcode.toPath(selected[0])
        paths_b = self.gcode.toPath(selected[1])
        if len(paths_a) != 1 or len(paths_b) != 1:
            self.app.event_generate(
                "<<Status>>", data=_("Each selected block must contain one path")
            )
            return

        try:
            contours = boolean_paths(paths_a[0], paths_b[0], operation)
        except ValueError as error:
            self.app.event_generate(
                "<<Status>>", data=_(str(error))
            )
            return

        if not contours:
            self.app.event_generate(
                "<<Status>>", data=_("The operation produced no graphics")
            )
            return

        block = Block(label)
        block.extend(self.gcode.fromPath(contours))
        position = max(selected) + 1
        self.gcode.addUndo(
            self.gcode.insBlocksUndo(position, [block]), label
        )
        self.fill()
        self.app.event_generate("<<Modified>>")
        self.app.event_generate(
            "<<Status>>", data=_("Generated: {}".format(label))
        )

    def intersectPaths(self, event=None):
        self._booleanPaths("intersection", _("Intersection"))

    def unionPaths(self, event=None):
        self._booleanPaths("union", _("Union"))

    def differencePaths(self, event=None):
        self._booleanPaths("difference", _("Difference A - B"))

    def symmetricDifferencePaths(self, event=None):
        self._booleanPaths("symmetric_difference", _("Symmetric Difference"))
