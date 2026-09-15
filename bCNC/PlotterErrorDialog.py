"""Tk presentation for classified errors; recovery policy lives separately."""
from PlotterErrors import friendly_error


def show_modal_error(workflow, parent, title, detail):
    import tkinter as tk
    from PlotterTheme import PANEL, INK, MUTED, BG
    previous_grab = parent.grab_current()
    from PlotterPages import WorkspacePage
    dialog = WorkspacePage(parent)
    dialog.title('Needs attention · Foil Studio')
    dialog.configure(bg=PANEL, padx=24, pady=20)
    dialog.transient(parent)
    heading, message, _, _ = friendly_error(title, str(detail))
    from PlotterUI import ScrollFrame
    content = ScrollFrame(dialog); content.pack(fill='both', expand=True)
    body = content.body
    tk.Label(body, text=heading, bg=PANEL, fg=INK, font=('DejaVu Sans', 17, 'bold'),
             wraplength=450, justify='left', anchor='w').pack(fill='x')
    tk.Label(body, text=message, bg=PANEL, fg=MUTED, font=('DejaVu Sans', 11),
             wraplength=450, justify='left', anchor='w').pack(fill='x', pady=14)
    technical = tk.Text(body, width=55, height=8, wrap='word', relief='flat', bg=BG)
    technical.insert('1.0', f'{title}\n\n{detail}')
    technical.config(state='disabled')
    def toggle():
        if technical.winfo_manager():
            technical.pack_forget()
            details.config(text='Show details')
        else:
            technical.pack(fill='both', expand=True)
            details.config(text='Hide details')
    def close():
        dialog.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
    buttons = tk.Frame(dialog, bg=PANEL)
    buttons.pack(side='bottom', fill='x', pady=8, before=content)
    row = workflow.button_grid(buttons, [('Show details', toggle), ('Copy details', lambda: (dialog.clipboard_clear(), dialog.clipboard_append(f'{title}\n{detail}')))])
    details = row.winfo_children()[0]
    workflow.button(buttons, 'Return to workspace', close, primary='alarm' not in title.lower()).pack(fill='x', pady=4)
    if 'alarm' in title.lower():
        workflow.button(buttons, 'Review machine', lambda: (close(), workflow.open_machine()), primary=True).pack(fill='x', pady=4)
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda event: close())
    from PlotterUI import fit_dialog
    fit_dialog(dialog, workflow.app, 540, 500)
    dialog.grab_set()
    return dialog
