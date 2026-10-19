#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Zensers Desktop Application Launcher
Creates a borderless, resizable standalone window using pywebview
Apple-style design - Title bar is a React built-in component, no CSS injection conflicts
"""

import subprocess
import sys
import time
import os
import logging
import threading
from pathlib import Path

# Network requests (for checking service status)
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Project root directory
PROJECT_ROOT = Path(__file__).parent
WEB_DIR = PROJECT_ROOT / "web"
BACKEND_PORT = int(os.environ.get('BACKEND_PORT', '8000'))
BACKEND_URL = os.environ.get('BACKEND_URL', f'http://localhost:{BACKEND_PORT}')

# Global window object
_window = None

# Desktop notifications
try:
    from plyer import notification as plyer_notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False
    logging.warning(
        'plyer not installed - desktop notifications disabled. '
        'Install with: pip install plyer'
    )


def show_notification(title: str, message: str):
    """Show system native notification (non-blocking)"""
    if not HAS_PLYER:
        return

    def _notify():
        try:
            plyer_notification.notify(
                title=title,
                message=message,
                app_name="Zensers",
                timeout=10,
            )
        except Exception:
            pass

    threading.Thread(target=_notify, daemon=True).start()


def check_new_version() -> dict | None:
    """Check for new version from backend API with retry"""
    if not HAS_REQUESTS:
        return None
    import requests
    import time

    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            resp = requests.get(
                f"{BACKEND_URL}/api/v1/version",
                timeout=3,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("is_latest") is False:
                return {
                    "version": data.get("remote_version", ""),
                    "release_notes": data.get("release_notes", ""),
                    "download_url": data.get("desktop_download_url", ""),
                    "release_url": data.get("release_url", ""),
                }
            return None
        except requests.ConnectionError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None
        except Exception:
            return None

    return None


def check_backend_running():
    """Check if backend is running"""
    if not HAS_REQUESTS:
        return False
    try:
        response = requests.get(f"{BACKEND_URL}/api/v1/health", timeout=3)
        return response.status_code == 200
    except:
        return False


FRONTEND_PORT = 3000


def check_frontend_running():
    """Check if frontend service is running on fixed port"""
    if not HAS_REQUESTS:
        return False
    try:
        response = requests.get(f"http://localhost:{FRONTEND_PORT}/", timeout=1)
        return response.status_code == 200
    except:
        return False


_PM2_CMD = None


def _pm2_cmd():
    """Get PM2 command path (with caching)"""
    global _PM2_CMD
    if _PM2_CMD:
        return _PM2_CMD

    import shutil
    pm2_path = shutil.which("pm2.cmd") or shutil.which("pm2")
    if pm2_path:
        _PM2_CMD = pm2_path
        return _PM2_CMD

    # Try global install
    try:
        print("  PM2 not installed, installing...")
        subprocess.run(["npm.cmd", "install", "-g", "pm2"], check=True, capture_output=True, timeout=30)
        pm2_path = shutil.which("pm2.cmd") or shutil.which("pm2") or "pm2.cmd"
        _PM2_CMD = pm2_path
        print(f"  PM2 installed successfully: {_PM2_CMD}")
        return _PM2_CMD
    except Exception as e:
        print(f"  PM2 installation failed: {e}, falling back to npx")
        _PM2_CMD = "npx.cmd"
        return _PM2_CMD


def check_pm2_running():
    """Check PM2-managed zensers-web process status"""
    pm2 = _pm2_cmd()
    try:
        result = subprocess.run(
            [pm2, "status", "zensers-web", "--no-color"],
            capture_output=True, timeout=10, cwd=WEB_DIR,
        )
        stdout = result.stdout.decode('utf-8', errors='replace')
        return "online" in stdout
    except Exception:
        return False


def start_frontend_via_pm2():
    """Start frontend service via PM2"""
    pm2 = _pm2_cmd()
    print(f"  PM2: {pm2}")
    print(f"  Config: {WEB_DIR / 'pm2.config.cjs'}")
    subprocess.Popen(
        [pm2, "start", str(WEB_DIR / "pm2.config.cjs")],
        cwd=WEB_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return True


def stop_frontend():
    """Stop frontend service via PM2"""
    pm2 = _pm2_cmd()
    try:
        subprocess.run(
            [pm2, "stop", str(WEB_DIR / "pm2.config.cjs")],
            cwd=WEB_DIR, timeout=10,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("  Frontend service stopped")
    except Exception as e:
        print(f"  PM2 stop timed out, force killing...")
        try:
            subprocess.run([pm2, "kill"], cwd=WEB_DIR, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  Frontend force killed")
        except Exception:
            print("  Warning: Could not stop PM2, port may still be occupied")


def _kill_port(port: int):
    """Kill any process occupying the specified port (Windows)"""
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            f'netstat -ano | findstr :{port} | findstr LISTENING',
            shell=True, capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if parts and len(parts) >= 5:
                pid = parts[-1]
                try:
                    subprocess.run(
                        f'taskkill /F /PID {pid}',
                        shell=True, capture_output=True, timeout=5
                    )
                    print(f"  Killed process {pid} on port {port}")
                except Exception:
                    pass
    except Exception:
        pass


def start_backend():
    """Start backend service"""
    if check_backend_running():
        print("  Backend service already running")
        return True

    print("Starting backend service...")
    _kill_port(BACKEND_PORT)

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    err_log = open(log_dir / "uvicorn_stderr.log", "w", encoding="utf-8")
    out_log = open(log_dir / "uvicorn_stdout.log", "w", encoding="utf-8")

    if sys.platform == "win32":
        subprocess.Popen(
            f'cmd /c "cd /d {PROJECT_ROOT} && python -m uvicorn src.api.main:app --host 127.0.0.1 --port {BACKEND_PORT}"',
            shell=True,
            stdout=out_log,
            stderr=err_log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen(
            f"cd {PROJECT_ROOT} && python -m uvicorn src.api.main:app --host 127.0.0.1 --port {BACKEND_PORT}",
            shell=True,
            stdout=out_log,
            stderr=err_log,
        )

    # Wait up to 60 seconds for backend to start (some systems are slow)
    for i in range(60):
        time.sleep(1)
        if check_backend_running():
            print("  Backend service started successfully")
            return True
        if i % 10 == 9:
            print(f"  Waiting for backend... ({i+1}s)")

    print("  Backend service startup timeout")
    return False


def start_frontend():
    """Start frontend service - prefer PM2, fallback to detecting existing process"""
    _kill_port(FRONTEND_PORT)

    # Check if frontend is already running
    if check_frontend_running():
        print(f"  Frontend service already running (port {FRONTEND_PORT})")
        return FRONTEND_PORT

    # Check if PM2 process is running
    if check_pm2_running():
        print("  PM2 process already running, waiting for service...")
    else:
        print("Starting frontend service (PM2)...")
        start_frontend_via_pm2()

    # Poll and wait for service to be ready (max 120 seconds)
    start_time = time.time()
    while time.time() - start_time < 120:
        if check_frontend_running():
            print(f"  Frontend service started successfully (port {FRONTEND_PORT})")
            return FRONTEND_PORT
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"  Waiting... ({elapsed}s)")
        time.sleep(2)

    print("  Frontend service startup timeout")
    return None


class Api:
    """API for JS-Python communication"""

    def __init__(self):
        self._maximized = False

    def move_window(self, x: int, y: int):
        """Move window to specified screen coordinates"""
        global _window
        if _window:
            _window.move(x, y)

    def minimize(self):
        """Minimize window"""
        global _window
        if _window:
            _window.minimize()

    def maximize(self):
        """Maximize/restore window"""
        global _window
        if _window:
            try:
                if self._maximized:
                    _window.restore()
                    self._maximized = False
                else:
                    _window.maximize()
                    self._maximized = True
            except Exception as e:
                print(f"Window operation failed: {e}")

    def close(self):
        """Close window"""
        global _window
        if _window:
            _window.destroy()

    def save_file(self, default_filename: str = "document.docx", file_type: str = "docx"):
        """
        Open native save file dialog and return selected path.

        Args:
            default_filename: Default filename suggestion
            file_type: File type filter (docx, pdf, html)

        Returns:
            Selected file path or None if cancelled
        """
        global _window
        if not _window:
            return None

        try:
            import webview

            file_types_map = {
                'docx': 'Word Document (*.docx)',
                'pdf': 'PDF Document (*.pdf)',
                'html': 'HTML Document (*.html)',
            }
            file_types = (file_types_map.get(file_type, file_types_map['docx']),)

            result = _window.create_file_dialog(
                webview.SAVE_DIALOG,
                directory='',
                save_filename=default_filename,
                file_types=file_types
            )

            if result and len(result) > 0:
                selected_path = result[0]
                print(f"[SAVE_FILE] User selected: {selected_path}")
                return selected_path

            return None

        except Exception as e:
            print(f"[SAVE_FILE] Error opening save dialog: {e}")
            import traceback
            traceback.print_exc()
            return None

    def download_and_save(self, url: str, default_filename: str = "document.docx", file_type: str = "docx"):
        """
        Open save dialog, download from URL, and save to selected location.

        Args:
            url: Download URL (relative to backend, e.g., /api/v1/download/{task_id})
            default_filename: Default filename suggestion
            file_type: File type filter (docx, pdf, html)

        Returns:
            Dict with success status and saved path or error message
        """
        import shutil
        import tempfile

        save_path = self.save_file(default_filename, file_type)
        if not save_path:
            return {"success": False, "error": "Cancelled by user"}

        try:
            full_url = f"{BACKEND_URL}{url}" if url.startswith('/') else url
            print(f"[DOWNLOAD_SAVE] Downloading from: {full_url}")

            response = requests.get(full_url, timeout=60)
            if response.status_code != 200:
                return {"success": False, "error": f"Download failed: HTTP {response.status_code}"}

            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_type}") as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name

            shutil.copy2(tmp_path, save_path)

            try:
                os.unlink(tmp_path)
            except:
                pass

            file_size = os.path.getsize(save_path)
            print(f"[DOWNLOAD_SAVE] Successfully saved to: {save_path} ({file_size} bytes)")

            return {
                "success": True,
                "path": save_path,
                "file_size": file_size,
            }

        except requests.RequestException as e:
            return {"success": False, "error": f"Network error: {e}"}
        except Exception as e:
            print(f"[DOWNLOAD_SAVE] Error: {e}")
            return {"success": False, "error": str(e)}


def _ensure_start_menu_shortcut():
    if sys.platform != 'win32':
        return
    try:
        from win32com.shell import shell, shellcon
        from win32com.propsys import propsys
        import pythoncom

        start_menu_dir = shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAMS, 0, 0)
        shortcut_dir = os.path.join(start_menu_dir, "Zensers")
        shortcut_path = os.path.join(shortcut_dir, "Zensers.lnk")
        icon_ico = str(PROJECT_ROOT / "icon.ico")
        target_script = str(PROJECT_ROOT / "desktop_app.py")

        os.makedirs(shortcut_dir, exist_ok=True)

        pythoncom.CoInitialize()
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        link.SetPath(sys.executable)
        link.SetArguments(f'"{target_script}"')
        link.SetWorkingDirectory(str(PROJECT_ROOT))
        link.SetDescription("Zensers Market Research System")
        if os.path.exists(icon_ico):
            link.SetIconLocation(icon_ico, 0)

        link.QueryInterface(pythoncom.IID_IPersistFile).Save(shortcut_path, 0)

        try:
            ps = propsys.SHGetPropertyStoreFromParsingName(
                shortcut_path, None, 0x00000002, propsys.IID_IPropertyStore
            )
            app_id_key = propsys.PSGetPropertyKeyFromName("System.AppUserModel.ID")
            pv = propsys.PROPVARIANTType('Zensers.MarketResearch.1.0')
            ps.SetValue(app_id_key, pv)
            ps.Commit()
        except Exception:
            pass

        print(f"  Start menu shortcut created: {shortcut_path}")
    except Exception:
        pass


def main():
    """Main function"""
    global _window

    # Windows taskbar icon setup
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'Zensers.MarketResearch.1.0'
            )
        except Exception as e:
            print(f"Set App ID failed: {e}")

        _ensure_start_menu_shortcut()

    print("=" * 50)
    print("  Zensers Market Research System")
    print("=" * 50)
    print()

    # Check dependencies
    try:
        import requests
    except ImportError:
        print("Error: Missing requests module")
        print("Please run: pip install requests")
        input("Press Enter to exit...")
        return

    try:
        import webview
    except ImportError:
        print("Error: Missing pywebview module")
        print("Please run: pip install pywebview")
        input("Press Enter to exit...")
        return

    # Start backend
    if not start_backend():
        print("Warning: Backend service failed to start, some features may be unavailable")

    # Start frontend
    frontend_port = start_frontend()
    if frontend_port is None:
        print("Error: Frontend service failed to start")
        input("Press Enter to exit...")
        return

    frontend_url = f"http://localhost:{frontend_port}/?desktop=1"

    print(f"Opening application window... ({frontend_url})")
    print()

    try:
        _window = webview.create_window(
            title="Zensers",
            url=frontend_url,
            width=1100,
            height=750,
            min_size=(900, 600),
            frameless=True,
            easy_drag=False,
            resizable=True,
            text_select=True,
            confirm_close=True,
            background_color="#1e1e20",
            js_api=Api(),
        )

        _icon_ico = str(PROJECT_ROOT / "icon.ico")
        if os.path.exists(_icon_ico):
            _window.icon = _icon_ico

        webview.start()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")
    finally:
        print()
        print("Stopping services...")
        stop_frontend()


if __name__ == "__main__":
    main()
