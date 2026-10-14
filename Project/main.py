"""Entry point for the terminal version. Wires the four layers together:

    user / file -> io_manager -> ai_manager -> logic_manager -> data_manager

Usage:
    python main.py                 interactive menu
    python main.py --batch         translate every meeting file in the input folder, then exit
    python main.py --meeting standup --a-name Acme --a-language English --b-name Mitra --b-language Indonesian

(The web version is app.py:  streamlit run app.py)
"""

import argparse
import logging
import os
import sys

import ai_manager
import data_manager
import io_manager
import logic_manager

LOG_PATH = os.environ.get("LOG_FILE", os.path.join("data", "app.log"))

def setup_logging():
    """Log to a file only, so all terminal output stays in io_manager."""
    folder = os.path.dirname(LOG_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
