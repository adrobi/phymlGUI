"""Registered engines, by key."""
from typing import Dict

from .base import Engine
from .phyml import PhyML

ENGINES: Dict[str, Engine] = {'phyml': PhyML()}
