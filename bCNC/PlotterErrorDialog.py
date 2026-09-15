"""Tk presentation for classified errors; recovery policy lives separately."""
from PlotterErrors import friendly_error


def show_modal_error(workflow, parent, title, detail):
    import tkinter as tk
    from PlotterTheme import PANEL, INK, MUTED
    previous_grab = parent.grab_current()
    dialog = tk.Toplevel(parent)
    dialog.title('Needs attention · Foil Studio')
    dialog.configure(bg=PANEL, padx=24, pady=20)
    dialog.transient(parent)
    heading, message, _, _ = friendly_error(title, str(detail))
    tk.Label(dialog, text=heading, bg=PANEL, fg=INK, font=('DejaVu Sans', 17, 'bold'),
             wraplength=450, justify='left', anchor='w').pack(fill='x')
    tk.Label(dialog, text=message, bg=PANEL, fg=MUTED, font=('DejaVu Sans', 11),
             wraplength=450, justify='left', anchor='w').pack(fill='x', pady=14)
    technical = tk.Text(dialog, width=55, height=8, wrap='word', relief='flat', bg='#f2f5f3')
    technical.insert('1.0', f'{title}\n\n{detail}')
    technical.config(state='disabled')
    def toggle():
        if technical.winfo_manager():
            technical.pack_forget()
            details.config(text='Show details')
        else:
            technical.pack(fill='both', expand=True, before=buttons)
            details.config(text='Hide details')
    def close():
        dialog.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
    buttons = tk.Frame(dialog, bg=PANEL)
    buttons.pack(fill='x', pady=8)
    details = workflow.button(buttons, 'Show details', toggle)
    details.pack(side='left')
    workflow.button(buttons, 'Back to editing', close, primary=True).pack(side='right', padx=(20, 0))
    dialog.protocol('WM_DELETE_WINDOW', close)
    dialog.bind('<Escape>', lambda event: close())
    dialog.grab_set()
    return dialog
