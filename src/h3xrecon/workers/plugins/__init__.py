"""
Plugin system for reconnaissance functions.
"""

from .base import ReconPlugin
import pkgutil
import importlib
from typing import Dict, Type

# Automatically discover and load all plugins
def load_plugins() -> Dict[str, Type[ReconPlugin]]:
    plugins = {}
    plugin_path = __path__[0] + '/recon'
    for _, name, _ in pkgutil.iter_modules([plugin_path]):
        module = importlib.import_module(f'.recon.{name}', package=__package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, ReconPlugin) and 
                attr != ReconPlugin):
                plugins[attr().name] = attr
    return plugins

__all__ = ['ReconPlugin', 'load_plugins']