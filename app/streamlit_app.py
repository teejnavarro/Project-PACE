# app/streamlit_app.py
# Streamlit entry point. Keeps ui.py importable as a normal module so app/views/* share one copy of it.
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from ui import main  # noqa: E402

main()
