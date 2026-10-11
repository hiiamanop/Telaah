#!/usr/bin/env python3
"""Pintasan pengembangan: python run.py (dari repo). Pemakai akhir: uvx telaah."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from telaah.cli import main  # noqa: E402

main()
