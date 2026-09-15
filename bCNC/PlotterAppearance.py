"""Semantic palette and density preferences for the workspace and its pages."""
import os
import subprocess
import tkinter as tk
from tkinter import ttk
import Utils

LIGHT = {'workspace':'#f3f5f6', 'surface':'#ffffff', 'text':'#20313c', 'muted':'#526571',
         'accent':'#176b5b', 'selected':'#e2f0ea', 'border':'#7a8993', 'divider':'#d7dfe3',
         'focus':'#245fc0', 'danger':'#b42318'}
DARK = dict(zip(LIGHT, ('#151b20','#202930','#edf2f4','#b3c0c9','#85d7c0','#25483f',
                       '#8597a3','#46545f','#a7c8ff','#ffb4ab')))


def system_dark():
    if 'dark' in os.environ.get('GTK_THEME', '').lower():
        return True
    try:
        return 'prefer-dark' in subprocess.run(['gsettings','get','org.gnome.desktop.interface','color-scheme'],
            capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


def apply_appearance(root, appearance=None, density=None, scope=None):
    from PlotterUI import descendants, RoundedButton
    if scope is not None and hasattr(root, '_appearance'):
        appearance = root._appearance
        density = root._density
    mode = appearance or Utils.getStr('Plotter', 'appearance', 'System')
    density = density or Utils.getStr('Plotter', 'density', 'Comfortable')
    dark = (getattr(root, '_dark', False) if scope is not None and hasattr(root, '_palette')
            else mode == 'Dark' or (mode == 'System' and system_dark()))
    root._dark = dark
    palette = DARK if dark else LIGHT
    mapping = {p[k]: palette[k] for p in (LIGHT, DARK) for k in LIGHT}
    root._palette = mapping
    root._appearance = mode
    root._density = density
    target = scope if scope is not None else root
    for child in [target, *descendants(target)]:
        if isinstance(child, ttk.Widget):
            continue
        values = {}
        for option in ('bg','fg','insertbackground','selectbackground','selectforeground','highlightbackground','highlightcolor','activebackground','activeforeground'):
            try:
                value = str(child.cget(option)).lower()
            except tk.TclError:
                continue
            if value in mapping:
                values[option] = mapping[value]
        if 'highlightbackground' in child.keys():
            values['highlightbackground'] = palette['surface']
        if isinstance(child, RoundedButton):
            if child._minimum_height < 56:
                values['minimum_height'] = 48 if density == 'Comfortable' or root.winfo_width() < 840 else 44
            if child.cget('bg') in (LIGHT['accent'], DARK['accent'], LIGHT['danger'], DARK['danger']):
                values['fg'] = DARK['surface'] if dark else LIGHT['surface']
            values['disabledforeground'] = palette['muted']
        if values:
            child.configure(**values)
    if scope is not None:
        return palette
    style = ttk.Style(root)
    for name in ('.', 'TFrame', 'TNotebook', 'TNotebook.Tab', 'TLabel', 'TCombobox', 'Foil.TCombobox', 'TEntry', 'Treeview'):
        style.configure(name, background=palette['surface'], foreground=palette['text'],
                        fieldbackground=palette['surface'], bordercolor=palette['border'])
    style.map('TNotebook.Tab', background=[('selected', palette['selected'])])
    style.map('Treeview', background=[('selected', palette['selected'])], foreground=[('selected', palette['text'])])
    style.map('Foil.TCombobox', fieldbackground=[('readonly',palette['surface'])])
    from PlotterUI import rounded_fields
    rounded_fields(root, palette['surface'], palette['border'], palette['selected'], palette['focus'])
    return palette


def save_appearance(root, appearance, density):
    Utils.setStr('Plotter', 'appearance', appearance)
    Utils.setStr('Plotter', 'density', density)
    return apply_appearance(root, appearance, density)
