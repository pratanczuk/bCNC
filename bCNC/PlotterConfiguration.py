"""Application configuration schema and validation without Tk widgets."""
import math
from PlotterPlanning import validate_plotter_commands

# Application preview/planning settings, not firmware values.
CONFIG_FIELDS = {
    **{f'travel_{a}': (f'{a.upper()} travel (mm)', 200 if a != 'z' else 100, 0.01, 100000) for a in 'xyz'},
    **{f'feedmax_{a}': (f'{a.upper()} maximum feed (mm/min)', 2000, 0.01, 100000) for a in 'xyz'},
    **{f'acceleration_{a}': (f'{a.upper()} acceleration (mm/s²)', 25, 0.01, 100000) for a in 'xyz'},
    'accuracy': ('Preview arc tolerance (mm)', 0.1, 0.001, 1),
    'round': ('Output decimal places', 4, 2, 6),
}


def validate_configuration(draft):
    values = {}
    for key, (title, default, low, high) in CONFIG_FIELDS.items():
        try:
            value = float(draft.get(key, default))
        except (TypeError, ValueError):
            raise ValueError(f"{title}: enter a number.") from None
        if not math.isfinite(value) or not low <= value <= high or (key == "round" and value != int(value)):
            raise ValueError(f"{title}: use {low:g}–{high:g}" + (" whole digits." if key == "round" else "."))
        values[key] = int(value) if key == "round" else value
    values.update(startup=draft.get("startup", "G90"))
    if "\x00" in values["startup"]:
        raise ValueError("Initialization commands cannot contain NUL characters.")
    validate_plotter_commands([], values["startup"])
    return values
