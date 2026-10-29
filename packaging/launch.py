"""Entry point for the frozen (PyInstaller) app. From source use:  python -m app.desktop"""
import sys

from app.desktop import main

if __name__ == '__main__':
    sys.exit(main())
