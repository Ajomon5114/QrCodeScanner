import os
import sys
import webbrowser
from threading import Timer
import time

def open_browser():
    time.sleep(1.5)
    print("Opening browser...")
    webbrowser.open("http://127.0.0.1:8000/")

if __name__ == "__main__":
    import threading
    
    # Force working directory to where the exe is located
    if getattr(sys, 'frozen', False):
        app_path = os.path.dirname(sys.executable)
        os.chdir(app_path)
        
        # Add the app path to sys.path
        sys.path.insert(0, app_path)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Start browser opener thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Run the server
    print("Starting CSI MKD Council 2026 Attendance Tracker...")
    execute_from_command_line([sys.argv[0], 'runserver', '127.0.0.1:8000', '--noreload'])
