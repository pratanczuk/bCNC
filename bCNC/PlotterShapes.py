"""Basic plotter shape generators. Algorithms by DodoLaSaumure."""
import math
from CNC import CNC, Block


class SimpleRectangle:
    def __init__(self, name):
        self.name = name

    def calc(self, xstart, ystart, xend, yend, radius, cw):
        self.corners = [
            min(float(xstart), float(xend)),
            min(float(ystart), float(yend)),
            max(float(xstart), float(xend)),
            max(float(ystart), float(yend)),
        ]

        xmin, ymin, xmax, ymax = (
            self.corners[0],
            self.corners[1],
            self.corners[2],
            self.corners[3],
        )
        r = min(radius, (xmax - xmin) / 2, (ymax - ymin) / 2)
        blocks = []
        block = Block(self.name)
        block.append(CNC.grapid(x=xmin, y=ymin + r))
        block.append(CNC.grapid(z=0.0))
        block.append("(entered)")
        if cw:
            block.append(CNC.gline(x=xmin, y=ymax - r))
            if r > 0:
                block.append(CNC.garc(2, x=xmin + r, y=ymax, i=r, j=0))
            if (xmax - xmin) > 2 * r:
                block.append(CNC.gline(x=xmax - r, y=ymax))
            if r > 0:
                block.append(CNC.garc(2, x=xmax, y=ymax - r, i=0, j=-r))
            if (ymax - ymin) > 2 * r:
                block.append(CNC.gline(x=xmax, y=ymin + r))
            if r > 0:
                block.append(CNC.garc(2, x=xmax - r, y=ymin, i=-r, j=0))
            if (xmax - xmin) > 2 * r:
                block.append(CNC.gline(x=xmin + r, y=ymin))
            if r > 0:
                block.append(CNC.garc(2, x=xmin, y=ymin + r, i=0, j=r))
        else:
            if r > 0:
                block.append(CNC.garc(3, x=xmin + r, y=ymin, i=r, j=0))
            if (xmax - xmin) > 2 * r:
                block.append(CNC.gline(x=xmax - r, y=ymin))
            if r > 0:
                block.append(CNC.garc(3, x=xmax, y=ymin + r, i=0, j=r))
            if (ymax - ymin) > 2 * r:
                block.append(CNC.gline(x=xmax, y=ymax - r))
            if r > 0:
                block.append(CNC.garc(3, x=xmax - r, y=ymax, i=-r, j=0))
            if (xmax - xmin) > 2 * r:
                block.append(CNC.gline(x=xmin + r, y=ymax))
            if r > 0:
                block.append(CNC.garc(3, x=xmin, y=ymax - r, i=0, j=-r))
            if (ymax - ymin) > 2 * r:
                block.append(CNC.gline(x=xmin, y=ymin + r))
        block.append("(exiting)")
        block.append(CNC.grapid(z=CNC.vars["safe"]))
        blocks.append(block)
        return blocks

class SimpleArc:
    def __init__(self, name):
        self.name = name

    def calc(self, xcenter, ycenter, radius, startangle, endangle):
        xcenter, ycenter, radius, startangle, endangle = (
            float(xcenter),
            float(ycenter),
            abs(float(radius)),
            float(startangle),
            float(endangle),
        )
        xstart = xcenter + radius * math.cos(startangle * math.pi / 180.0)
        xend = xcenter + radius * math.cos(endangle * math.pi / 180.0)
        ystart = ycenter + radius * math.sin(startangle * math.pi / 180.0)
        yend = ycenter + radius * math.sin(endangle * math.pi / 180.0)
        i = xcenter - xstart
        j = ycenter - ystart
        blocks = []
        block = Block(self.name)
        block.append(CNC.grapid(x=xstart, y=ystart))
        block.append(CNC.grapid(z=0.0))
        block.append("(entered)")
        if startangle < endangle:
            direction = 3
        else:
            direction = 2
        block.append(CNC.garc(direction, x=xend, y=yend, i=i, j=j))
        block.append("(exiting)")
        block.append(CNC.grapid(z=CNC.vars["safe"]))
        blocks.append(block)
        return blocks
