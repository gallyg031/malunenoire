import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, ROOT)

import astro  # noqa: E402

astro.set_ephe(os.path.join(ROOT, "data", "ephe"))
