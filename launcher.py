"""
ScanTrack Launcher — bundles Django into a standalone EXE.
Double-click to start the server and open the browser automatically.
"""
import sys
import os
import threading
import time
import webbrowser
import subprocess

# Prevent crash when running as a windowed application (where stdout/stderr are None)
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# ── Fix paths when running as a frozen EXE ──────────────────
if getattr(sys, 'frozen', False):
    # Running as EXE - base dir is the temp folder PyInstaller extracts to
    BASE_DIR = sys._MEIPASS
    # Also set the working directory to where the EXE lives
    # so the database (db.sqlite3) stays next to the EXE
    os.chdir(os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Put the project on the Python path
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

PORT = 8000
URL  = f'http://127.0.0.1:{PORT}'


def open_browser():
    """Wait for server to start, then launch browser."""
    time.sleep(2.5)
    webbrowser.open(URL)


def run_server():
    """Start the Django development server."""
    import django
    django.setup()
    from django.core.management import call_command
    call_command('runserver', f'0.0.0.0:{PORT}', '--noreload')


if __name__ == '__main__':
    print(f"Starting ScanTrack on {URL} ...")
    print("Press Ctrl+C to stop.\n")

    # Open browser in background thread
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    # Run Django server (blocks until killed)
    run_server()
