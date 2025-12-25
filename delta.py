"""
Convenience imports for Delta package.

Usage:
    from delta import Diagram
"""

from delta.diagram import Diagram
from delta.version import get_app_version

__version__ = get_app_version()
__all__ = ["Diagram", "__version__"]
