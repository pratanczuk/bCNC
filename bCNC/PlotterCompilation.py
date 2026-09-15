"""Compile a detached cut document before submitting commands to transport."""
from copy import deepcopy
from queue import Queue
from CNC import GCode


def compile_buffer(blocks, stop=None):
    document = GCode()
    document.blocks = deepcopy(blocks)
    commands = Queue()
    paths = document.compile(commands, stop)
    if paths is None:
        raise InterruptedError('Cut preparation cancelled.')
    if not paths:
        raise ValueError('There are no cutting commands in this design.')
    return tuple(commands.queue)
