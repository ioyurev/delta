"""
Delta - Ternary Phase Diagram Tool

Headless API:
    from delta import Diagram
    
    d = Diagram(["A", "B", "C"])
    d.add_point("X", 0.5, 0.3, 0.2)
    d.save_image("out.png")
"""

from delta.diagram import Diagram
from delta.version import get_app_version

__version__ = get_app_version()
__all__ = ["Diagram", "__version__"]