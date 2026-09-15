"""Preview-first layout, contour editing, weeding and material-layer views."""
from copy import deepcopy
import uuid
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk
from CNC import CNC, Block, GCode
from PlotterDesign import DesignDialog
from PlotterTheme import PANEL, BG, INK, MUTED, ACCENT
from PlotterEditing import bounds, transform, layout, fit, repair, weed_lines, contour_points
from PlotterProject import commit, changed_block, metadata


def preview_map(canvas, paths):
    x0,y0,x1,y1=bounds(paths)
    w,h=max(1,canvas.winfo_width()),max(1,canvas.winfo_height())
    margin=min(24,w/5,h/5)
    scale=min((w-2*margin)/max(x1-x0,.001),(h-2*margin)/max(y1-y0,.001))
    ox,oy=(w-(x1-x0)*scale)/2,(h-(y1-y0)*scale)/2
    return lambda point:(ox+(point[0]-x0)*scale,h-oy-(point[1]-y0)*scale)


def paint_path(canvas, path, point, color, dash=()):
    coordinates=[value for p in contour_points(path) for value in point(p)]
    if len(coordinates)>=4: canvas.create_line(*coordinates,fill=color,width=2,dash=dash)


class SelectionDialog(DesignDialog):
    def __init__(self, workflow, title):
        super().__init__(workflow,title)
        self.ids=workflow.selection()
        self.original=[(b,list(b),metadata(b),b.enable) for b in self.app.gcode.blocks]
        self.source={i:self.app.gcode.toPath(i) for i in self.ids}
        self.insert_button.config(text='Apply')

    def option(self,title,values,initial=None):
        self.workflow.label(self.controls,title,bold=True).pack(anchor='w',pady=(8,4))
        var=tk.StringVar(self,initial or values[0])
        combo=ttk.Combobox(self.controls,textvariable=var,values=values,state='readonly',width=24,style='Foil.TCombobox',font=('DejaVu Sans',11))
        combo.pack(fill='x'); combo.bind('<<ComboboxSelected>>',self.schedule)
        return var

    def compact(self,title,value):
        row=tk.Frame(self.controls,bg=PANEL); row.pack(fill='x',pady=5)
        self.workflow.label(row,title,size=10).pack(anchor='w')
        var=tk.StringVar(self,value)
        Field(row,textvariable=var,width=8,bg=BG,fg=INK,relief='flat',font=('DejaVu Sans',11)).pack(fill='x',ipady=8)
        var.trace_add('write',self.schedule)
        return var

    def valid_source(self):
        if self.app.sender.running: return False
        current=self.app.gcode.blocks
        if len(current)!=len(self.original) or any(b is not old or list(b)!=lines or metadata(b)!=props or b.enable!=enabled
                for b,(old,lines,props,enabled) in zip(current,self.original)):
            self.message.set('The artwork changed. Reopen this tool to preview the current selection.')
            return False
        return True

    def apply_blocks(self,blocks,title):
        commit(self.app.gcode,blocks,title)
        self.app.refresh(); self.workflow.confirmed.set(False); self.workflow.update_state()
        self.app.after_idle(self.workflow.fit_mat); self.destroy(); return True


class ArrangeDialog(SelectionDialog):
    """Stage transformations against a snapshot; commit one undo record."""
    def __init__(self, workflow):
        super().__init__(workflow, 'Size & arrange')
        box = bounds([p for paths in self.source.values() for p in paths])
        self.width = self.field('Width · mm', f'{box[2]-box[0]:g}')
        self.angle = self.field('Rotation · degrees', '0')
        self.x = self.field('Left edge · mm', f'{box[0]:g}')
        self.y = self.field('Bottom edge · mm', f'{box[1]:g}')
        self.horizontal = tk.BooleanVar(self, False)
        self.vertical = tk.BooleanVar(self, False)
        for text, var in [('Flip horizontal', self.horizontal), ('Flip vertical', self.vertical)]:
            tk.Checkbutton(self.controls, text=text, variable=var, command=self.schedule, bg=PANEL).pack(fill='x')
        workflow.button(self.controls, 'Center on mat', self.center).pack(fill='x', pady=8)
        self.insert_button.configure(text='Apply changes')
        self.schedule()

    def make_paths(self):
        import math
        from PlotterEditing import number, multiply
        source = [p for paths in self.source.values() for p in paths]
        x0, y0, x1, y1 = bounds(source)
        scale = number(self.width.get().replace(',', '.'), .001) / max(x1-x0, .001)
        angle = math.radians(number(self.angle.get().replace(',', '.')))
        sx = -scale if self.horizontal.get() else scale
        sy = -scale if self.vertical.get() else scale
        matrix = [sx*math.cos(angle), sx*math.sin(angle), -sy*math.sin(angle), sy*math.cos(angle), 0, 0]
        box = bounds(transform(source, matrix))
        self.matrix = multiply([1, 0, 0, 1, number(self.x.get().replace(',', '.'))-box[0],
                               number(self.y.get().replace(',', '.'))-box[1]], matrix)
        return transform(source, self.matrix)

    def center(self):
        self.rebuild()
        if self.paths:
            box = bounds(self.paths)
            self.x.set(f"{(CNC.vars['mat_width']-box[2]+box[0])/2:g}")
            self.y.set(f"{(CNC.vars['mat_height']-box[3]+box[1])/2:g}")

    def insert(self):
        if not self.valid_source():
            return False
        self.rebuild()
        if not self.paths:
            return False
        blocks = list(self.app.gcode.blocks)
        for i in self.ids:
            blocks[i] = changed_block(self.app.gcode, blocks[i], transform(self.source[i], self.matrix), self.matrix, preserve_text=True)
        return self.apply_blocks(blocks, 'Arrange objects')


class LayoutDialog(SelectionDialog):
    def __init__(self,workflow):
        super().__init__(workflow,'Layout & repeat')
        self.units=[]; groups={}
        for i in self.ids:
            key=metadata(self.app.gcode.blocks[i]).get('group') or f'object-{i}'
            if key not in groups: groups[key]=[]; self.units.append(groups[key])
            groups[key].append(i)
        self.operation=self.option('Operation',['Align left','Align right','Align top','Align bottom',
            'Center horizontally','Center vertically','Distribute horizontal','Distribute vertical','Repeat grid','Pack on mat'])
        self.target=self.option('Align relative to',['Selection','Mat'])
        self.rows=self.compact('Rows','1'); self.columns=self.compact('Columns','2')
        self.gap=self.compact('Gap · mm','5'); self.margin=self.compact('Packing margin · mm','10')
        workflow.label(self.controls,'Attached groups move as one unit. Repeat preserves the whole arrangement. Packing uses rectangular shelves without rotation.',muted=True).pack(fill='x',pady=12)
        self.schedule()

    def make_paths(self):
        groups=[[p for i in unit for p in self.source[i]] for unit in self.units]
        self.placements=layout(groups,self.operation.get(),CNC.vars['mat_width'],CNC.vars['mat_height'],
            target=self.target.get(),rows=self.rows.get(),columns=self.columns.get(),gap=self.gap.get(),margin=self.margin.get())
        return [p for index,matrix in self.placements for p in transform(groups[index],matrix)]

    def insert(self):
        if not self.valid_source(): return False
        self.rebuild()
        if not self.paths: return False
        added=[]
        for index,matrix in self.placements:
            group=uuid.uuid4().hex if len(self.units[index])>1 else ''
            for i in self.units[index]:
                block=changed_block(self.app.gcode,self.app.gcode.blocks[i],transform(self.source[i],matrix),matrix,preserve_text=True)
                if group: block.foil['group']=group
                block.foil.setdefault('source_outlines',[contour_points(p) for p in self.source[i]])
                added.append(block)
        first=min(self.ids)
        blocks=[b for i,b in enumerate(self.app.gcode.blocks) if i not in self.ids]
        blocks[first:first]=added
        return self.apply_blocks(blocks,self.operation.get())


class ContourDialog(SelectionDialog):
    def __init__(self,workflow):
        super().__init__(workflow,'Contours & nodes')
        self.flat=[p for i in self.ids for p in self.source[i]]
        self.operation=self.option('Operation',['Move node','Insert node','Delete node','Hide contour','Close gap','Simplify'])
        self.contour=self.option('Contour',[str(i+1) for i in range(len(self.flat))] or ['1'])
        self.tolerance=self.compact('Gap / deviation · mm','.1')
        self.node=self.compact('Node index (from 0)','0')
        first=self.flat[0][0].A if self.flat else (0,0)
        self.x=self.compact('Node X · mm',str(first[0])); self.y=self.compact('Node Y · mm',str(first[1]))
        self.nodes=tk.Listbox(self.controls,height=7,bg=BG,fg=INK,exportselection=False)
        self.nodes.pack(fill='both',expand=True,pady=8)
        self.nodes.bind('<<ListboxSelect>>',self.choose_node)
        self.loaded=None
        self.node_positions=[]
        self._drag_map = None
        self.preview.bind('<Button-1>',self.pick_node)
        self.preview.bind('<B1-Motion>',self.drag_node)
        self.preview.bind('<ButtonRelease-1>',self.release_node)
        workflow.label(self.controls,'Drag a node in the preview, or select it below and enter coordinates. Choose Apply to keep the edit. Curves use a 0.02 mm polyline approximation. Applying converts selected artwork to editable outlines; Undo restores text and groups.',muted=True).pack(fill='x')
        self.schedule()

    def choose_node(self,event=None):
        indices=self.nodes.curselection()
        if not indices: return
        points=contour_points(self.flat[int(self.contour.get())-1]); index=indices[0]
        self.node.set(str(index)); self.x.set(f'{points[index][0]:g}'); self.y.set(f'{points[index][1]:g}')

    def make_paths(self):
        index=int(self.contour.get())-1
        if self.flat and self.loaded!=index:
            self.nodes.delete(0,'end')
            for j,p in enumerate(contour_points(self.flat[index])):
                self.nodes.insert('end',f'{j}:  {p[0]:.3f}, {p[1]:.3f}')
            self.loaded=index
        return repair(self.flat,self.operation.get(),index,self.tolerance.get(),self.node.get(),self.x.get(),self.y.get())

    def rebuild(self):
        super().rebuild()
        if not self.paths and self.operation.get()=='Hide contour' and len(self.flat)==1:
            self.message.set('This removes the last contour. Gray shows the original. Undo restores it.')
            self.error_button.pack_forget()
            self.insert_button.config(state='normal')

    def draw_preview(self):
        if not hasattr(self,'flat'): return
        self.preview.delete('all'); self.node_positions=[]
        if not self.flat: return
        point=self._drag_map or preview_map(self.preview,self.flat+self.paths)
        self._preview_map=point
        for path in self.flat: paint_path(self.preview,path,point,'#a9b4b0',(3,3))
        for path in self.paths: paint_path(self.preview,path,point,ACCENT)
        try:
            index=int(self.contour.get())-1; selected=int(self.node.get())
            visible=self.paths if self.operation.get()=='Move node' and self.paths else self.flat
            self.node_positions=[point(p) for p in contour_points(visible[index])]
            for i,(x,y) in enumerate(self.node_positions):
                self.preview.create_oval(x-3,y-3,x+3,y+3,fill='#b47a12' if i==selected else PANEL,outline=INK)
            if 0<=selected<len(self.node_positions):
                x,y=self.node_positions[selected]
                self.preview.create_text(x+10,y-12,text=f'Node {selected}',anchor='w',fill=INK)
        except (ValueError,IndexError): pass

    def pick_node(self,event):
        if not self.node_positions: return
        index=min(range(len(self.node_positions)),key=lambda i:(self.node_positions[i][0]-event.x)**2+(self.node_positions[i][1]-event.y)**2)
        x,y=self.node_positions[index]
        if (x-event.x)**2+(y-event.y)**2>144: return
        same = str(index) == self.node.get()
        self.nodes.selection_clear(0,'end'); self.nodes.selection_set(index); self.nodes.see(index)
        if not same:
            self.choose_node()
        if self.operation.get() == 'Move node':
            try:
                origin = (event.x, event.y, float(self.x.get().replace(',', '.')), float(self.y.get().replace(',', '.')))
            except ValueError:
                return
            self._drag_map = self._preview_map
            self._drag_origin = origin

    def drag_node(self, event):
        if self._drag_map is None or self.operation.get() != 'Move node':
            return
        if (self.app.sender.running or self.app.mat_handling.active or self.app.tool_sequence.active):
            self._drag_map = None
            return
        px, py, x, y = self._drag_origin
        a, b = self._drag_map((0, 0)), self._drag_map((1, 1))
        self.x.set(f'{x + (event.x-px)/(b[0]-a[0]):.6f}')
        self.y.set(f'{y + (event.y-py)/(b[1]-a[1]):.6f}')
        # Variable traces debounce numeric typing; dragging needs immediate feedback.
        self.rebuild()

    def release_node(self, event):
        if self._drag_map is not None:
            self.drag_node(event)
            self._drag_map = None
            self.draw_preview()

    def insert(self):
        if not self.valid_source(): return False
        try:
            paths=self.make_paths()
            if paths: fit([paths],CNC.vars['mat_width'],CNC.vars['mat_height'])
        except ValueError as error: self.message.set(str(error)); return False
        # Replace only the object that owns this contour; other objects/layers stay intact.
        offset=0; selected=int(self.contour.get())-1
        for i in self.ids:
            count=len(self.source[i])
            if offset<=selected<offset+count:
                local=repair(self.source[i],self.operation.get(),selected-offset,self.tolerance.get(),self.node.get(),self.x.get(),self.y.get())
                blocks=list(self.app.gcode.blocks)
                if local: blocks[i]=changed_block(self.app.gcode,blocks[i],local)
                else: del blocks[i]
                return self.apply_blocks(blocks,self.operation.get())
            offset+=count
        return False


class WeedDialog(SelectionDialog):
    def __init__(self,workflow):
        super().__init__(workflow,'Weeding lines')
        self.spacing=self.compact('Row spacing · mm','20')
        self.clearance=self.compact('Artwork clearance · mm','1')
        self.margin=self.compact('Border margin · mm','3')
        workflow.label(self.controls,'Horizontal weed cuts stop before the artwork. Enclosed holes remain protected. Inspect the preview before adding these separate cuts.',muted=True).pack(fill='x',pady=14)
        self.insert_button.config(text='Add weed cuts'); self.schedule()

    def make_paths(self):
        paths=weed_lines(list(self.source.values()),self.spacing.get(),self.clearance.get(),self.margin.get())
        fit([paths],CNC.vars['mat_width'],CNC.vars['mat_height']); return paths

    def insert(self):
        if not self.valid_source(): return False
        self.rebuild()
        if not self.paths: return False
        block=self.app.gcode.fromPath(self.paths,z=0); block._name='Weeding cuts'
        layers={metadata(self.app.gcode.blocks[i]).get('layer','Default') for i in self.ids}
        if len(layers)!=1:
            self.message.set('Select artwork from one material layer before adding weed cuts.'); return False
        block.foil={'layer':layers.pop(),'vector':True}
        blocks=list(self.app.gcode.blocks)
        index=next((i for i,b in enumerate(blocks) if b.name()=='Footer'),len(blocks))
        blocks.insert(index,block)
        return self.apply_blocks(blocks,'Add weeding cuts')


from PlotterLayersUI import LayersDialog


class CutPreviewDialog(DesignDialog):
    def __init__(self,workflow):
        super().__init__(workflow,'Cut sequence preview')
        self.cancel_button.pack_forget()
        self.insert_button.config(text='Done',command=self.destroy)
        self.order=tk.BooleanVar(self,bool(CNC.vars.get('mat_inner_first',False)))
        tk.Checkbutton(self.controls,text='Inner contours before outer',variable=self.order,bg=PANEL,
                       command=self.change_order).pack(anchor='w',pady=8)
        self.position=tk.IntVar(self,0)
        self.slider=ttk.Scale(self.controls,variable=self.position,from_=0,to=1,orient='horizontal',
                             command=lambda value:self.draw_preview())
        self.slider.pack(fill='x')
        workflow.label(self.controls,'Solid green: cut outlines. Dashed orange: travel between outlines. Numbers show the sequence. Drag the slider to inspect progress. This sends nothing to the plotter.',muted=True).pack(fill='x',pady=12)
        workflow.label(self.controls,'The preview includes blade compensation. Multi-tool sequences draw with pens first, then cut with knives. Each physical tool change requires your confirmation; homing and travel between passes are not shown.',muted=True).pack(fill='x',pady=12)
        self.schedule()

    def change_order(self):
        CNC.vars['mat_inner_first']=self.order.get()
        self.workflow.confirmed.set(False); self.schedule()

    def make_paths(self):
        job=GCode(); job.blocks=self.app.plotter.preview()
        paths=[p for i,b in enumerate(job.blocks) if b.enable and b.name() not in ('Header','Footer') for _ in range(b.passes) for p in job.toPath(i)]
        self.slider.config(to=max(1,len(paths))); self.position.set(len(paths))
        return paths

    def draw_preview(self):
        if not hasattr(self,'position'): return
        self.preview.delete('all')
        if not self.paths: return
        point=preview_map(self.preview,self.paths)
        previous=None
        for i,path in enumerate(self.paths,1):
            active=i<=self.position.get()
            paint_path(self.preview,path,point,ACCENT if active else '#d6ddda')
            start=point(path[0].A)
            if previous and active:
                self.preview.create_line(*previous,*start,fill='#b47a12',dash=(4,3),arrow='last')
            if active: self.preview.create_text(start[0]+7,start[1]-8,text=str(i),fill=INK)
            previous=point(path[-1].B)


class ProjectsDialog(WorkspacePage):
    def __init__(self,workflow):
        super().__init__(workflow.app)
        self.workflow=workflow; self.app=workflow.app
        self.title('Local projects · Foil Studio'); self.configure(bg=PANEL,padx=24,pady=20)
        self.geometry('740x640'); self.transient(self.app)
        footer=tk.Frame(self,bg=PANEL); footer.pack(side='bottom',fill='x',pady=(8,0))
        workflow.button(footer,'Close',self.destroy).pack(side='right')
        from PlotterUI import ScrollFrame
        scroller = ScrollFrame(self); scroller.pack(fill='both', expand=True)
        body = scroller.body
        heading=workflow.label(body,'Your local projects',size=20,bold=True); heading.config(wraplength=680); heading.pack(anchor='w')
        description=workflow.label(body,'Editable projects keep text, layers and groups. G-code export is for cutting.',muted=True); description.config(wraplength=680); description.pack(fill='x',pady=10)
        workflow.button_grid(body,[('New project',lambda:self.navigate(workflow.new_design)),('Import artwork…',lambda:self.navigate(workflow.import_artwork))])
        workflow.button_grid(body,[('Open project…',self.open),('Save project…',self.save)])
        workflow.button(body,'Export prepared cut G-code…',workflow.project.export_cut).pack(fill='x',pady=4)
        workflow.label(body,'Recent projects',bold=True).pack(anchor='w',pady=(16,4))
        self.recent=workflow.project.recent()
        self.list=tk.Listbox(body,height=5,bg=BG,fg=INK,exportselection=False)
        self.list.pack(fill='x')
        for name in self.recent: self.list.insert('end',name)
        workflow.button(body,'Open selected recent project',self.open_recent).pack(fill='x',pady=4)
        self.recoveries=workflow.project.recoveries()
        workflow.label(body,'Recovery copies',bold=True).pack(anchor='w',pady=(12,4))
        self.recovery_list=tk.Listbox(body,height=3,bg=BG,fg=INK,exportselection=False)
        self.recovery_list.pack(fill='x')
        from datetime import datetime
        for path in self.recoveries:
            self.recovery_list.insert('end',datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')+' · '+path.name[:8])
        workflow.button_grid(body,[('Recover selected copy',self.recover),('First-cut guide',self.guide)])
        self.bind('<Escape>',lambda e:self.destroy()); self.grab_set()

    def navigate(self, command):
        self.destroy()
        command()

    def open(self):
        if self.workflow.project.open():
            self.destroy(); self.workflow.show_step(0)
    def save(self):
        if self.workflow.project.save(): self.destroy()
    def open_recent(self):
        ids=self.list.curselection()
        if ids and self.workflow.project.open(self.recent[ids[0]]):
            self.destroy(); self.workflow.show_step(0)
    def recover(self):
        ids=self.recovery_list.curselection()
        if ids and self.workflow.project.open(self.recoveries[ids[0]],recovery=True):
            self.destroy(); self.workflow.show_step(0)
    def guide(self):
        self.destroy(); self.workflow.design_dialog('FirstCutDialog')


class FirstCutDialog(WorkspacePage):
    def __init__(self,workflow):
        super().__init__(workflow.app)
        self.workflow=workflow
        self.title('Your first cut · Foil Studio')
        self.configure(bg=PANEL, padx=24, pady=16)
        self.step=getattr(workflow,'guide_step',0)
        footer=tk.Frame(self,bg=PANEL);footer.pack(side='bottom',fill='x')
        self.action=workflow.button(footer,'',self.perform,primary=True);self.action.pack(fill='x',pady=8)
        workflow.button_grid(footer,[('Back',lambda:self.move(-1)),('Next',lambda:self.move(1))])
        workflow.button(footer,'Close guide',self.destroy).pack(fill='x',pady=8)
        from PlotterUI import ScrollFrame
        scroller=ScrollFrame(self);scroller.pack(fill='both',expand=True)
        self.heading=workflow.label(scroller.body,'',size=20,bold=True);self.heading.pack(fill='x')
        self.text=workflow.label(scroller.body,'',size=12);self.text.pack(fill='x',pady=24)
        self.bind('<Escape>',lambda e:self.destroy());self.show()

    def show(self):
        steps=[('1 · Connect your plotter','Connect USB and switch on the plotter. Choose the port and GRBL firmware. Return here after the connection succeeds.','Connection setup'),
               ('2 · Set blade and pressure','Expose only enough blade to cut the foil. Choose pressure, speed, blade offset and overcut. Changing settings here does not move the blade.','Pressure & blade settings'),
               ('3 · Make a small test','Save your artwork, then create a separate square, circle and corner test. Use scrap material attached securely to the mat.','Create test design'),
               ('4 · Position the mat','Align the mat, set the origin in Prepare and confirm it. Review the cut preview. You must press Start cut yourself; this guide never starts motion.','Go to Prepare'),
               ('5 · Check the result','Peel the foil. The backing should remain intact. Reduce pressure or blade exposure if the backing is cut; adjust offset for rounded or hooked corners. Make another small test after each adjustment.','Finish')]
        steps[2], steps[3] = steps[3], steps[2]
        title,text,action=steps[self.step]
        title = str(self.step+1) + title[1:]; self.heading.config(text=title); self.text.config(text=text); self.action.config(text=action)
    def move(self,delta): self.step=max(0,min(4,self.step+delta)); self.show()
    def perform(self):
        step=self.step; self.workflow.guide_step=min(4,step+1); self.destroy()
        if step==0: self.workflow.connection_settings()
        elif step==1: self.workflow.settings('Material')
        elif step==2: self.workflow.show_step(1)
        elif step==3: self.workflow.new_calibration()
