"""UI-independent command and recovery policies. Parsing is injected."""
import re


def validate_plotter_commands(blocks, startup, *, compile_line, break_line):
    """Reject retired operations before any part of a job reaches the sender.

    Keep Z lift, PWM, dwell, modal positioning and arcs. This check is deliberately
    limited to operations removed from this fork; GRBL still validates G-code.
    """
    lines = list(startup.splitlines())
    for block in blocks:
        if block.enable:
            lines.extend(block)
    for line in lines:
        compiled = compile_line(line)
        if not isinstance(compiled, str):
            continue
        for word in break_line(compiled) or []:
            try:
                value = float(word[1:])
            except ValueError:
                continue
            if ((word[0].upper() == 'G' and
                 (38 <= value < 39 or 81 <= value < 90 or value in (98, 99)))
                    or (word[0].upper() == 'M' and value == 6)):
                raise ValueError(
                    f"{word.upper()} is a probing, drilling or tool-change command. "
                    "Use a planar cutting file and set the blade in Material and blade settings.")


def can_unlock(state):
    match = re.search(r'\balarm\s*:\s*(\d+)', state, re.I)
    # Critical hardware faults and homing-required states need their own recovery.
    return bool(match and int(match.group(1)) in {3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 18})
