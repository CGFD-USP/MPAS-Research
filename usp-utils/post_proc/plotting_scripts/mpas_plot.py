#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED thin shim — kept for backward compatibility.

The plotting/animation logic now lives in the unified ``mpas_viz.py``. This
wrapper forwards to it so existing commands and aliases keep working:

    python mpas_plot.py -f x1.10242.sfc_update.nc -v sst -t 0 -o sst.png

Prefer calling ``mpas_viz.py`` directly. All the public functions are still
importable from here for any code that did ``from mpas_plot import ...``.
"""

from mpas_viz import *          # noqa: F401,F403  (re-export public API)
from mpas_viz import main

if __name__ == "__main__":
    main()
