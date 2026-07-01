"""Compatibility wrapper for the top-level ICA benchmark package.

New ICA benchmark logic belongs in `ica.*`. Studio backend imports this module
only for legacy compatibility with existing routes, scripts, and tests.
"""

from ica.benchmark import *  # noqa: F401,F403
from ica.benchmark import _company_harvester_input_from_materialized  # noqa: F401
