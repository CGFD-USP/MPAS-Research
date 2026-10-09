#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEPRECATED thin shim — kept for backward compatibility.

The plotting/animation logic now lives in the unified ``mpas_viz.py``. This
wrapper forwards to it so existing commands and aliases keep working:

    python mpas_animate.py -f "history.*.nc" -v surface_pressure --tmin 0 --tmax 10 -o anim.mp4

(``--tmin``/``--tmax`` are accepted as aliases of ``--tstart``/``--tend``.)

Prefer calling ``mpas_viz.py`` directly. All the public functions are still
importable from here for any code that did ``from mpas_animate import ...``.
"""

from mpas_viz import *          # noqa: F401,F403  (re-export public API)
from mpas_viz import main

if __name__ == "__main__":
    main()
