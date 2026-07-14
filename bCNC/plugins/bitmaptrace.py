"""Register Image Trace without colliding with the tracing helper module."""

import importlib.util
import os


_source = os.path.join(os.path.dirname(__file__), "imagetrace.py")
_spec = importlib.util.spec_from_file_location("_bcnc_imagetrace_plugin", _source)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

Tool = _module.Tool