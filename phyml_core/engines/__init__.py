"""Registered engines, by key."""
from typing import Dict

from .base import Engine
from .iqtree import IqTree
from .phyml import PhyML

ENGINES: Dict[str, Engine] = {'phyml': PhyML(), 'iqtree': IqTree()}
