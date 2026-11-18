"""Terminal entry point:  python main.py [--batch] [--meeting NAME ...]"""

import sys

from meeting_translator.cli import Application

if __name__ == "__main__":
    sys.exit(Application.main())
