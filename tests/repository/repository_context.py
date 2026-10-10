"""Paths for repository integration tests; never required by a standalone skill."""
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
SKILL=REPO/'.agents/skills/hydraulic-schematic'
SCRIPTS=SKILL/'scripts'
sys.path.insert(0,str(SCRIPTS))
