"""`python -m rlcoach` runs the command line, as the background server does."""

import sys

from .cli import main

sys.exit(main())
