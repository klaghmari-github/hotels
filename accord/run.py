#!/usr/bin/env python3
"""
Point d'entrée CLI d'Accord Data Studio.

Usage
-----
    cd accord
    python run.py
    python run.py --port 8080 --debug

Délègue à ``app.main()`` (Flask).
"""

from app import main

if __name__ == "__main__":
    main()
