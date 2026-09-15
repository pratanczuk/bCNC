"""Material and tool library editor. Edits never send machine commands."""
from PlotterUI import AutoScrollbar
import tkinter as tk
from PlotterUI import Field
from PlotterPages import WorkspacePage
from tkinter import ttk, messagebox, colorchooser
from PlotterTheme import PANEL, INK, MUTED
from PlotterLibrary import validate_profile


class LibraryDialog(WorkspacePage):
    def __init__(self, workflow):
        super().__init__(workflow.app)
        self.workflow = workflow
        self.library = workflow.library
        self.title('Materials & tools · Foil Studio')
        self.geometry('900x710'); self.minsize(800, 630)
        self.configure(bg=PANEL); self.transient(workflow.app)
        self.message = tk.StringVar(self)
        self.forms, self.lists, self.selected_names, self.widgets, self.rows = {}, {}, {}, {}, {}
        self.searches = {}
        self.details = {}
        top = tk.Frame(self, bg=PANEL, padx=20, pady=4); top.pack(fill='x')
        title = workflow.label(top, 'Materials & tools', size=20, bold=True)
        title.configure(wraplength=750); title.pack(side='left')
        from PlotterUI import ChoiceButton
        context=tk.IntVar(self,0)
        for index,title in reversed(list(enumerate(('Materials','Tools')))):
            ChoiceButton(top,text=title,variable=context,value=index,command=lambda:book.select(context.get())).pack(side='right',padx=3)
        bottom = tk.Frame(self, bg=PANEL, padx=20, pady=6); bottom.pack(side='bottom', fill='x')
        workflow.button(bottom, 'Done', self.destroy, primary=True).pack(side='right')
        tk.Label(bottom, textvariable=self.message, wraplength=620, justify='left', anchor='w', bg=PANEL, fg=INK).pack(side='left', fill='x',expand=True)
        style=ttk.Style(self);style.layout('LibraryContext.TNotebook.Tab',[])
        book = ttk.Notebook(self,style='LibraryContext.TNotebook'); book.pack(fill='both', expand=True, padx=20)
        book.bind('<<NotebookTabChanged>>',lambda e:context.set(book.index('current')))
        definitions = {
            'materials': [('name','Name',None),('speed','Preset speed · mm/min',None),('pressure','Preset pressure · 0–1000',None),
                          ('thickness','Thickness · mm (reference)',None),('passes','Passes',None),
                          ('compatible','Compatible tools',('Both','Knife','Pen')),('notes','Notes',None)],
            'tools': [('name','Name',None),('kind','Tool type',('Knife','Pen')),('angle','Blade angle · degrees (reference)',None),
                      ('offset','Blade offset · mm',None),('overcut','Overcut · mm',None),('compensate','Drag-knife compensation',('On','Off')),
                      ('width','Pen stroke width · mm (reference)',None),('color','Pen color · #RRGGBB',None),('notes','Notes',None)]}
        for kind, fields in definitions.items():
            page = tk.Frame(book, bg=PANEL, padx=8, pady=4); book.add(page, text=kind.title())
            left = tk.Frame(page, bg=PANEL); left.pack(side='left', fill='y', padx=(0,20))
            search = tk.StringVar(self)
            self.searches[kind] = search
            workflow.label(left, 'Search ' + kind).pack(anchor='w')
            ttk.Entry(left, textvariable=search).pack(fill='x', pady=8)
            search.trace_add('write', lambda *args, k=kind: self.refresh(k))
            listing = tk.Listbox(left, width=25, font=('DejaVu Sans',11), exportselection=False, bd=0,
                                 bg='#f1f5f7', fg=INK, selectbackground='#166c5e', selectforeground='white')
            listing.pack(fill='both', expand=True); self.lists[kind] = listing
            listing.bind('<<ListboxSelect>>', lambda e, k=kind: self.select(k))
            actions = tk.Frame(left, bg=PANEL)
            actions.pack(side='bottom', fill='x', pady=6, before=listing)
            for index, (label, action) in enumerate([('Add', self.new),('Duplicate', self.duplicate),('Delete', self.delete)]):
                actions.columnconfigure(index, weight=1)
                workflow.button(actions, label, lambda a=action,k=kind: a(k)).grid(row=0, column=index, sticky='ew', padx=2)
            right = tk.Frame(page, bg=PANEL); right.pack(side='left', fill='both', expand=True)
            footer = tk.Frame(right, bg=PANEL); footer.pack(side='bottom', fill='x', pady=8)
            workflow.button(footer, 'Save preset', lambda k=kind:self.save(k)).pack(side='left', pady=2)
            workflow.button(footer, 'Use in Prepare' if kind == 'materials' else 'Use on selected layer', lambda k=kind:self.use_on_layer(k), primary=True).pack(side='right', pady=2)
            sections = ttk.Notebook(right); sections.pack(fill='both',expand=True)
            groups = ({'Cut settings': ('name','speed','pressure','passes'),
                       'Details': ('thickness','compatible','notes')} if kind == 'materials' else
                      {'Tool': ('name','kind','angle','offset'), 'Blade': ('overcut','compensate'),
                       'Appearance': ('width','color','notes')})
            forms = {}
            from PlotterUI import ScrollFrame
            for title, keys in groups.items():
                scroller=ScrollFrame(sections);sections.add(scroller,text=title)
                scroller.canvas.configure(height=1)
                form=scroller.body
                for col in (0,1): form.columnconfigure(col,weight=1,uniform='fields')
                for index,key in enumerate(keys): forms[key]=(form,index)
            self.forms[kind], self.widgets[kind], self.rows[kind] = {}, {}, {}
            for key,label,choices in fields:
                form,index=forms[key]
                row = tk.Frame(form,bg=PANEL);row.grid(row=index//2,column=index%2,sticky='ew',padx=4,pady=2);self.rows[kind][key]=row
                workflow.label(row,label,size=10).pack(anchor='w',pady=(2,2))
                var = tk.StringVar(self); self.forms[kind][key] = var
                widget = ttk.Combobox(row,textvariable=var,values=choices,state='readonly',style='Foil.TCombobox',width=10) if choices else ttk.Entry(row,textvariable=var,width=10,font=('DejaVu Sans',11))
                widget.pack(fill='x'); self.widgets[kind][key] = widget
                if kind=='tools' and key=='color':
                    self.color_button=workflow.button(row,'Choose color…',self.pick_color)
                    self.color_button.pack(fill='x',pady=2)
                if key == 'kind': widget.bind('<<ComboboxSelected>>',lambda e:self.tool_changed())
            if kind == 'tools':
                form=forms['compensate'][0]
                self.tool_note = workflow.label(form,'',muted=True,size=10)
                self.tool_note.configure(wraplength=470); self.tool_note.grid(row=2,column=0,columnspan=2,sticky='ew',pady=4)
            self.refresh(kind); self.new(kind)
            from PlotterUI import ListDetail
            # List/detail becomes a stacked, scrollable form on a narrow screen.
            if not hasattr(self, 'adaptive_splits'):
                self.adaptive_splits = []
            self.details[kind] = ListDetail(page, left, right)
            self.adaptive_splits.append(self.details[kind])
        self.bind('<Escape>',lambda e:self.destroy())
        self.grab_set()

    def refresh(self, kind, selected=None):
        listing = self.lists[kind]; listing.delete(0,'end')
        for name in sorted(self.library.records[kind]):
            if self.searches[kind].get().casefold() in name.casefold():
                listing.insert('end',name)
        if selected:
            names = list(listing.get(0, 'end'))
            if selected in names:
                listing.selection_set(names.index(selected))
                self.select(kind)

    def new(self, kind):
        if kind in self.details:
            self.details[kind].show_detail()
        self.selected_names[kind] = None
        self.lists[kind].selection_clear(0,'end')
        defaults = validate_profile(kind, {'name':'New material' if kind=='materials' else 'New tool'})
        defaults['name'] = ''
        self.populate(kind, defaults)
        self.message.set('Enter a name and settings, then Save changes. Existing layer setups stay unchanged.')

    def populate(self, kind, record):
        for key,var in self.forms[kind].items():
            item = record[key]
            var.set(('On' if item else 'Off') if key=='compensate' else str(item))
        if kind=='tools': self.tool_changed()

    def use_on_layer(self, kind):
        name = self.selected_names[kind]
        if kind == 'materials':
            if not name:
                self.message.set('Select a saved material first.')
                return
            self.workflow.refresh_library()
            self.workflow.material.set(name)
            self.workflow.apply_material()
            self.destroy()
            self.workflow.show_step(1)
            return
        if not name or not self.workflow.selection():
            self.message.set('Select artwork and a saved preset first.')
            return
        from PlotterLayersUI import LayersDialog
        from PlotterUI import fit_dialog
        page = LayersDialog(self.workflow)
        page.tree.selection_set(page.tree.parent('object:' + str(self.workflow.selection()[0])))
        page.selected()
        page.tool_profile.set(name)
        if kind == 'tools':
            page.operation.set('Draw' if self.library.records[kind][name]['kind'] == 'Pen' else 'Cut')
        page.adaptive_split.show_detail()
        page.message.set('Review the selected layer setup, then Apply tool & operation.')
        fit_dialog(page, self.workflow.app)

    def select(self, kind):
        if kind in self.details:
            self.details[kind].show_detail()
        selection = self.lists[kind].curselection()
        if not selection: return
        name = self.lists[kind].get(selection[0]); self.selected_names[kind] = name
        self.populate(kind, self.library.records[kind][name])

    def tool_changed(self):
        pen = self.forms['tools']['kind'].get() == 'Pen'
        for key in ('angle','offset','overcut','compensate'):
            if pen: self.forms['tools'][key].set('Off' if key=='compensate' else '0')
            self.widgets['tools'][key].configure(state='disabled' if pen else 'readonly' if key=='compensate' else 'normal')
        if not pen and self.forms['tools']['angle'].get()=='0': self.forms['tools']['angle'].set('45')
        for row in self.rows['tools'].values(): row.grid_remove()
        hidden = ('angle','offset','overcut','compensate') if pen else ('width','color')
        for key, row in self.rows['tools'].items():
            if key not in hidden: row.grid()
        self.tool_note.configure(text='Pen paths use no drag-knife compensation or overcut. Stroke width describes the physical pen; it does not widen the drawing paths.' if pen else 'Blade angle is a reference for choosing your physical knife. Offset and overcut affect the prepared cutting paths.')
        if pen: self.color_button.pack(fill='x')
        else: self.color_button.pack_forget()

    def pick_color(self):
        chosen = colorchooser.askcolor(parent=self, title='Pen color')[1]
        if chosen: self.forms['tools']['color'].set(chosen)

    def save(self, kind):
        if self.workflow.app.sender.running or self.workflow.app.mat_handling.active:
            self.message.set('Wait until the plotter finishes.'); return
        try:
            raw = {key:var.get() for key,var in self.forms[kind].items()}
            if kind=='tools': raw['compensate'] = raw['compensate']=='On'
            name = self.library.save(kind,raw,self.selected_names[kind])
            self.workflow.save_library(); self.refresh(kind,name)
            self.message.set('Saved. To update an existing layer, select this profile there and apply its setup again.')
        except ValueError as error: self.message.set(str(error))

    def duplicate(self, kind):
        name = self.selected_names[kind]
        if name:
            name = self.library.duplicate(kind,name)
            self.workflow.save_library(); self.refresh(kind,name)

    def delete(self, kind):
        name = self.selected_names[kind]
        if name and messagebox.askyesno('Delete profile',f'Delete “{name}” from the library? Existing project layers keep their saved setup.',parent=self):
            self.library.delete(kind,name); self.workflow.save_library(); self.refresh(kind); self.new(kind)
