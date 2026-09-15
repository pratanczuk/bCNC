"""Local project, recent-file and crash-recovery integration for the workflow."""
from pathlib import Path
import json
import time
import uuid
from tkinter import filedialog
import Utils
from CNC import CNC
import PlotterProject as project


class ProjectSession:
    def __init__(self, workflow):
        self.workflow=workflow; self.app=workflow.app
        self.directory=Path(Utils.iniUser).parent / 'foil-recovery'
        self.recovery=self.directory/(uuid.uuid4().hex+'.foil')
        self.last_check=0; self.last_state=None; self.failed=False

    def data(self):
        return project.snapshot(self.app.gcode,(CNC.vars['mat_width'],CNC.vars['mat_height']))

    def recent(self):
        try:
            values=json.loads(Utils.getStr('Plotter','recent_projects','[]'))
            return [p for p in values if isinstance(p,str)][:12] if isinstance(values,list) else []
        except ValueError: return []

    def remember(self, filename):
        filename=str(Path(filename).resolve())
        Utils.addSection('Plotter')
        Utils.setStr('Plotter','recent_projects',json.dumps([filename]+[p for p in self.recent() if p!=filename][:11]))
        self.app.saveConfig()

    def save(self, filename=None):
        if self.app.sender.running: return False
        try:
            if not filename:
                current=self.app.gcode.filename or ''
                filename=current if current.lower().endswith('.foil') else filedialog.asksaveasfilename(
                    parent=self.app,title='Save editable project',defaultextension='.foil',filetypes=[('Foil Studio project','*.foil')])
            if not filename: return False
            if Path(filename).suffix.lower()!='.foil':
                raise ValueError('Use the .foil extension for editable projects. Use Export prepared cut G-code for machine files.')
            project.write(filename,self.data())
            self.app.gcode.filename=str(filename); self.app.gcode._modified=False
            self.remember(filename); self.clear_recovery(); self.workflow.update_state()
            return True
        except (OSError,ValueError) as error:
            self.app.reportPlotterError('Could not save project',str(error)); return False

    def export_cut(self, filename=None):
        if self.app.sender.running: return False
        try:
            from CNC import GCode
            document=GCode()
            document.blocks=self.app.plotter.prepare()
            if not filename:
                filename=filedialog.asksaveasfilename(parent=self.app,title='Export prepared cut G-code',
                    defaultextension='.ngc',filetypes=[('GRBL cut file','*.ngc')])
            if not filename: return False
            if Path(filename).suffix.lower()=='.foil':
                raise ValueError('Use .ngc for cut export. Use Save project for editable .foil files.')
            if not document.save(filename): raise OSError('The cut file could not be written.')
            return True
        except (OSError,ValueError) as error:
            self.app.reportPlotterError('Could not export cut',str(error)); return False

    def open(self, filename=None, recovery=False):
        if self.app.sender.running: return False
        if not filename:
            filename=filedialog.askopenfilename(parent=self.app,title='Open editable project',filetypes=[('Foil Studio project','*.foil')])
        if not filename: return False
        try:
            blocks,mat=project.read(filename)  # Validate fully before touching current work.
            if self.app.fileModified(): return False
            self.app.gcode.init(); self.app.gcode.blocks=blocks
            self.app.gcode.foil_layers=blocks.layers
            self.app.gcode.filename='' if recovery else str(filename)
            self.app.gcode._modified=bool(recovery)
            CNC.vars['mat_width'],CNC.vars['mat_height']=mat
            self.workflow.confirmed.set(False); self.workflow._cut_started=False
            self.workflow.import_filename='Recovered project' if recovery else Path(filename).name
            self.app.refresh(); self.workflow.show_step(0); self.workflow.fit_mat()
            if not recovery: self.remember(filename)
            return True
        except (OSError,ValueError) as error:
            self.app.reportPlotterError('Could not open project',str(error)); return False

    def recoveries(self):
        return sorted((p for p in self.directory.glob('*.foil') if p!=self.recovery),key=lambda p:p.stat().st_mtime,reverse=True)

    def clear_recovery(self):
        self.recovery.unlink(missing_ok=True)
        self.last_state=None

    def tick(self):
        if time.monotonic()-self.last_check<30: return
        self.last_check=time.monotonic()
        if self.app.sender.running or not self.app.gcode.isModified(): return
        try:
            data=self.data()
            if data!=self.last_state:
                self.directory.mkdir(parents=True,exist_ok=True)
                project.write(self.recovery,data); self.last_state=data
            self.failed=False
        except (OSError,ValueError) as error:
            if not self.failed:
                self.failed=True
                self.app.reportPlotterError('Recovery copy unavailable',str(error))
