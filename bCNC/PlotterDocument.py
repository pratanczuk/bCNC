"""Document transactions independent of Tk and the Application object.

The existing GCode document provides block edits and the single undo stack.
"""
from CNC import Block


class JobCodeTransaction:
    """Stage header/footer edits against the document that opened the editor."""
    def __init__(self, document):
        self.document = document
        self.snapshot = [(block, list(block)) for block in document.blocks]
        self.original = {}
        for name in ('Header', 'Footer'):
            blocks = [block for block in document.blocks if block.name() == name]
            self.original[name] = '\n'.join(blocks[0]) if blocks else getattr(document, name.lower())

    def validate(self, draft):
        if set(draft) != set(self.original) or any(not isinstance(text, str) for text in draft.values()):
            raise ValueError('Provide both a header and a footer.')
        if any('\x00' in text for text in draft.values()):
            raise ValueError('Header and footer cannot contain NUL characters.')
        changed = draft != self.original
        if changed:
            blocks = self.document.blocks
            if len(blocks) != len(self.snapshot) or any(
                    current is not old or list(current) != lines
                    for current, (old, lines) in zip(blocks, self.snapshot)):
                raise ValueError('The job changed while settings were open. Reopen settings before editing its G-code.')
            if any(sum(block.name() == name for block in blocks) > 1 for name in draft):
                raise ValueError('This job has duplicate header/footer blocks. Remove duplicate blocks before editing job G-code.')
        return changed

    def commit(self, draft):
        if not self.validate(draft):
            return False
        undo = []
        for name, text in draft.items():
            index = next((i for i, block in enumerate(self.document.blocks) if block.name() == name), None)
            if text == self.original[name] and index is not None:
                continue
            if index is None:
                block = Block(name)
                block.extend(text.splitlines())
                undo.append(self.document.insBlocksUndo(0 if name == 'Header' else len(self.document.blocks), [block]))
            else:
                undo.append(self.document.setBlockLinesUndo(index, text.splitlines()))
        self.document.addUndo(undo, 'Edit job header and footer')
        return True
