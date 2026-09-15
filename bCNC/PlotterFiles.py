"""Document import/export and recent paths, independent of machine transport."""
from pathlib import Path
import Utils


class DocumentFiles:
    def __init__(self, document):
        self.document = document

    def remember(self, filename):
        path = Path(filename).absolute()
        Utils.setUtf('File', 'dir', str(path.parent))
        Utils.setUtf('File', 'file', path.name)
        Utils.addRecent(str(filename))

    @staticmethod
    def extension(filename):
        extension = Path(filename).suffix.lower()
        if extension in ('.probe', '.orient', '.xyz', '.stl', '.ply'):
            raise ValueError('Use SVG, DXF or GRBL cut files. This file format is not supported.')
        return extension

    def load(self, filename):
        extension = self.extension(filename)
        if extension in ('.dxf', '.svg'):
            self.document.init()
            if extension == '.dxf':
                self.document.importDXF(filename)
            else:
                self.document.importSVG(filename)
        elif not self.document.load(filename):
            raise OSError('Could not read the drawing file.')
        self.remember(filename)

    def save(self, filename):
        extension = self.extension(filename)
        if extension == '.dxf':
            return self.document.saveDXF(filename)
        if extension == '.svg':
            return self.document.saveSVG(filename)
        if extension == '.txt':
            return self.document.saveTXT(filename)
        self.document.filename = filename
        result = self.document.save()
        if result:
            self.remember(filename)
        return result
