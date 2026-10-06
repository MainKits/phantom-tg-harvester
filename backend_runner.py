"""
Entry point for PyInstaller — starts the uvicorn server.
"""
import sys
import os

# When running as PyInstaller bundle, fix the working directory
if getattr(sys, 'frozen', False):
    # The app is running as a bundle
    bundle_dir = os.path.dirname(sys.executable)
    os.chdir(bundle_dir)
    sys.path.insert(0, bundle_dir)

import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )
