# -*- coding: utf-8 -*-
"""Compatibility entrypoint; current rendering and gates live only in the skill."""
from pathlib import Path
import runpy
import sys

HERE=Path(__file__).resolve().parent
SCRIPTS=HERE.parent/'.agents/skills/hydraulic-schematic/scripts'
sys.path.insert(0,str(SCRIPTS))
if __name__=='__main__':
    target=SCRIPTS/'render_l0_sheet.py'
    sys.argv=[str(target),*(sys.argv[1:] or [str(HERE)])]
    runpy.run_path(str(target),run_name='__main__')
