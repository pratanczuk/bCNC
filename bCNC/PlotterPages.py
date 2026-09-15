"""In-workspace pages: retained drafts, focus restoration and stable job controls."""
import tkinter as tk
from PlotterTheme import PANEL


class WorkspacePage(tk.Frame):
    """A former dialog hosted in the application's content region."""
    def __init__(self, parent, **kwargs):
        self.app_root = parent.winfo_toplevel()
        self._page_title = ''
        self._close = self.destroy
        self._return_focus = self.app_root.focus_get()
        self._shown = False
        super().__init__(self.app_root, bg=PANEL, **kwargs)
        self.bind('<Escape>', lambda event: self._close())
        self._resize_id = self.app_root.bind('<Configure>', self._resize, add='+')

    def title(self, value=None):
        if value is not None:
            self._page_title = value
        return self._page_title

    def geometry(self, value=None):
        if value is None:
            return f'{self.winfo_width()}x{self.winfo_height()}'
        return None

    def minsize(self, *args):
        return (320, 400)

    def resizable(self, *args):
        return (True, True)

    def transient(self, *args):
        return self.app_root

    def protocol(self, name, callback=None):
        if name == 'WM_DELETE_WINDOW' and callback:
            self._close = callback
        return self._close

    def grab_set(self):
        # Workspace navigation and persistent Stop remain available.
        return None

    def present(self):
        self._shown = True
        stack = getattr(self.app_root, 'workspace_pages', [])
        if self not in stack:
            stack.append(self)
        self.app_root.workspace_pages = stack
        self._resize()
        self.lift()
        workflow = getattr(self.app_root, 'workflow', None)
        if workflow and getattr(workflow, 'adaptive_ready', False):
            workflow.update_state()

    def _resize(self, event=None):
        area = getattr(self.app_root, 'paned', self.app_root)
        if not self._shown or (event is not None and event.widget not in (self.app_root, area)):
            return
        app = self.app_root
        area = getattr(app, 'paned', app)
        self.place(x=area.winfo_x(), y=area.winfo_y(), width=area.winfo_width(), height=area.winfo_height())

    def destroy(self):
        if not self.winfo_exists():
            return
        app = self.app_root
        app.unbind('<Configure>', self._resize_id)
        app.workspace_pages = [p for p in getattr(app, 'workspace_pages', []) if p is not self and p.winfo_exists()]
        super().destroy()
        if app.workspace_pages:
            app.workspace_pages[-1].lift()
        if self._return_focus is not None and self._return_focus.winfo_exists():
            self._return_focus.focus_set()
        workflow = getattr(app, 'workflow', None)
        if workflow and getattr(workflow, 'adaptive_ready', False):
            workflow.update_state()


def ask_save_changes(app):
    """Filename-specific Save / Discard / Cancel without destructive defaults."""
    import os
    from PlotterUI import RoundedButton, fit_dialog
    from PlotterTheme import INK, ACCENT
    page = WorkspacePage(app)
    page.configure(padx=24, pady=24)
    name = os.path.basename(app.gcode.filename or 'Untitled project')
    tk.Label(page, text='Save changes?', bg=PANEL, fg=INK, font=('DejaVu Sans', 20, 'bold')).pack(anchor='w')
    tk.Label(page, text=f'Changes to {name} have not been saved.', bg=PANEL, fg=INK,
             wraplength=280, justify='left').pack(fill='x', pady=24)
    result = ['cancel']
    def choose(value):
        result[0] = value
        page.destroy()
    for label, value in [('Save project', 'yes'), ('Discard changes', 'no'), ('Keep editing', 'cancel')]:
        RoundedButton(page, text=label, command=lambda v=value: choose(v),
                      bg=ACCENT if value == 'yes' else PANEL, fg='white' if value == 'yes' else INK).pack(fill='x', pady=8)
    fit_dialog(page, app)
    page.wait_window()
    return result[0]
