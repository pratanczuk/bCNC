"""Trace bitmap images as contours, centerlines, or sticker cut paths."""

from CNC import Block
from ToolsPage import Plugin
from bmath import Vector
from bpath import Path, Segment
from imagetrace import trace_image

__name__ = _("Image Trace")
__version__ = "1.0"


class Tool(Plugin):
    __doc__ = _("Convert bitmap artwork to vector contours or centerlines")

    def __init__(self, master):
        Plugin.__init__(self, master, "ImageTrace")
        self.icon = "heightmap"
        self.group = "Generator"
        self.variables = [
            ("name", "db", "", _("Name")),
            ("File", "file", "", _("Image to process")),
            (
                "Mode",
                "Contours,Multi-threshold,Centerline,Print then cut",
                "Contours",
                _("Trace mode"),
            ),
            ("Threshold", "int", 128, _("Dark threshold (0-255)")),
            ("Thresholds", "int", 4, _("Multi-threshold levels")),
            ("Invert", "bool", False, _("Invert luminance")),
            ("RemoveBackground", "bool", True, _("Remove edge background")),
            ("BackgroundTolerance", "int", 24, _("Background tolerance")),
            ("MinArea", "int", 16, _("Minimum area (pixels)")),
            ("Simplify", "float", 1.0, _("Contour smoothing (pixels)")),
            ("SpurLength", "int", 4, _("Centerline spur length")),
            ("MaxSize", "mm", 100.0, _("Maximum output size")),
            ("Bleed", "mm", 0.0, _("Print-cut outward bleed")),
            ("Depth", "mm", 0.0, _("Working depth")),
        ]
        self.buttons.append("exe")

    @staticmethod
    def _to_paths(pixel_paths, image_height, scale, name, closed):
        paths = []
        for points in pixel_paths:
            converted = []
            for x, y in points:
                point = Vector(x * scale, (image_height - y) * scale)
                if not converted or point != converted[-1]:
                    converted.append(point)
            if len(converted) < 2:
                continue
            path = Path(name)
            for start, end in zip(converted, converted[1:]):
                path.append(Segment(Segment.LINE, start, end))
            if closed and converted[0] != converted[-1]:
                path.append(Segment(Segment.LINE, converted[-1], converted[0]))
            if path:
                paths.append(path)
        return paths

    def execute(self, app):
        try:
            from PIL import Image
            image = Image.open(self["File"])
        except Exception:
            app.setStatus(_("Image Trace abort: Can't read image file"))
            return

        maximum = self.fromMm("MaxSize")
        if maximum <= 0:
            app.setStatus(_("Image Trace abort: Maximum output size must be positive"))
            return

        width, height = image.size
        longest_side = max(width, height)
        scale = maximum / float(longest_side)
        threshold = max(0, min(255, int(self["Threshold"])))
        tolerance = max(0, int(self["BackgroundTolerance"]))
        min_area = max(0, int(self["MinArea"]))
        simplify = max(0.0, float(self["Simplify"]))
        mode = self["Mode"]
        try:
            records = trace_image(
                image,
                mode=mode,
                threshold=threshold,
                levels=self["Thresholds"],
                invert=self["Invert"],
                remove_background=self["RemoveBackground"],
                tolerance=tolerance,
                minimum_area=min_area,
                simplify=simplify,
                spur_length=int(self["SpurLength"]),
                bleed_pixels=self.fromMm("Bleed") / scale,
            )
        except RuntimeError as error:
            app.setStatus(_("Image Trace abort: %s") % error)
            return

        paths = []
        for path_name, pixel_path, closed in records:
            paths.extend(
                self._to_paths(
                    [pixel_path], height, scale, path_name, closed
                )
            )

        if not paths:
            app.setStatus(_("Image Trace: no paths found"))
            return

        name = self["name"]
        if not name or name == "default":
            name = "Image Trace"
        block = app.gcode.fromPath(paths, z=self.fromMm("Depth"))
        block._name = name
        active = app.activeBlock()
        if active == 0:
            active = 1
        app.gcode.insBlocks(active, [block], "Image Trace")
        app.refresh()
        app.setStatus(_("Image Trace: generated %d paths") % len(paths))