# ---------------------- Imports ----------------------
import ctypes
import os
import sys
import time
import threading
import subprocess
import comtypes
from datetime import datetime, timedelta
from copy import deepcopy
import winreg
import json

from pycaw.pycaw import AudioUtilities
from pycaw.constants import AudioSessionState
from monitorcontrol import get_monitors

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QSlider,
    QLabel, QVBoxLayout, QHBoxLayout, QFrame, QComboBox
)
from PySide6.QtGui import QIcon, QCursor, QAction, QGuiApplication
from PySide6.QtCore import Qt, QPoint, QObject, QTimer

# ---------------------- Idle Detection ----------------------
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]

def get_idle_time_seconds():
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    elapsed_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return elapsed_ms / 1000.0

USE_WHITELIST_BLOCK_MODE = False #False = for production 

def is_media_playing():
    sessions = AudioUtilities.GetAllSessions()
    ignored_players = SETTINGS.get("ignored_media_players", [])

    for session in sessions:
        if session.State == AudioSessionState.Active:
            try:
                process_name = session.Process.name().lower()

                if USE_WHITELIST_BLOCK_MODE:
                    if any(ignored_player.lower() in process_name for ignored_player in ignored_players):
                        return True
                else:
                    if not any(ignored_player.lower() in process_name for ignored_player in ignored_players):
                        return True
            except:
                continue
    return False

# ---------------------- Monitors ----------------------
_monitors_cache = list(get_monitors())

def get_brightness(monitor_index=0):
    try:
        with _monitors_cache[monitor_index] as m:
            return m.get_luminance()
    except Exception:
        return None

def set_brightness(value, monitor_index=0):
    try:
        with _monitors_cache[monitor_index] as m:
            m.set_luminance(value)
    except Exception:
        pass

# ---------------------- Screensaver ----------------------
# Screensaver paths
exe_path = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__), "overlay.exe")

def start_screensaver():
    subprocess.Popen([exe_path, "--show"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def kill_screensaver():
    subprocess.Popen([exe_path, "--close"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
# ---------------------- Settings ----------------------
EXE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
SETTINGS_PATH = os.path.join(EXE_DIR, "settings.json")

DEFAULT_SETTINGS_WRAPPED = {
    "tray_ui_enabled": {
        "value": True,
        "description": "Enable or disable the tray UI"
    },
    "idle_threshold": {
        "value": 120,
        "description": "Seconds of user inactivity before triggering screensaver"
    },
    "media_grace_period": {
        "value": 15,
        "description": "Seconds after media stops before screensaver triggers"
    },
    "slider_min": {
        "value": 1,
        "description": "Minimum brightness for slider"
    },
    "slider_max": {
        "value": 100,
        "description": "Maximum brightness for slider"
    },
    "ignored_media_players": {
        "value": [
            "spotify.exe",
            "winamp.exe",
            "dopamine.exe"
        ],
        "description": "Processes to ignore when detecting media playback. Normally, any active media prevents the screensaver, but apps in this list are treated as exceptions (e.g., background music players). This way, listening to music won’t stop the screensaver from starting."
    }
}

DEFAULT_SETTINGS = {key: val["value"] for key, val in DEFAULT_SETTINGS_WRAPPED.items()}

def extract_values(settings_obj):
    return {
        key: entry["value"]
        for key, entry in settings_obj.items()
        if isinstance(entry, dict) and "value" in entry
    }

def load_settings():
    try:
        with open(SETTINGS_PATH, "r") as f:
            raw = json.load(f)
        settings = extract_values(raw)
        return {key: settings.get(key, DEFAULT_SETTINGS[key]) for key in DEFAULT_SETTINGS}
    except Exception:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(DEFAULT_SETTINGS_WRAPPED, f, indent=4)
        python = sys.executable
        os.execl(python, python, *sys.argv)

SETTINGS = load_settings()
IDLE_THRESHOLD = SETTINGS.get("idle_threshold", 120)
MEDIA_GRACE_PERIOD = timedelta(seconds=int(SETTINGS.get("media_grace_period", 15)))
TRAY_UI = SETTINGS.get("tray_ui_enabled", True)
CHECK_INTERVAL = 1

# ---------------------- Main Loop ----------------------
def main_loop():
    global SCREENSAVER_ACTIVE, last_media_detected
    comtypes.CoInitialize()
    try:
        SCREENSAVER_ACTIVE = False
        last_media_detected = datetime.min
        media_start_time = None

        while True:
            idle_time = get_idle_time_seconds()
            current_time = datetime.now()
            media_playing = is_media_playing()

            if media_playing:
                last_media_detected = current_time

            in_grace_period = (current_time - last_media_detected) <= MEDIA_GRACE_PERIOD

            if idle_time > IDLE_THRESHOLD:
                if not SCREENSAVER_ACTIVE and not in_grace_period:
                    start_screensaver()
                    SCREENSAVER_ACTIVE = True
                elif SCREENSAVER_ACTIVE:
                    if media_playing:
                        if media_start_time is None:
                            media_start_time = current_time
                        elif (current_time - media_start_time).total_seconds() >= 10:
                            kill_screensaver()
                            SCREENSAVER_ACTIVE = False
                    else:
                        media_start_time = None
            elif SCREENSAVER_ACTIVE:
                kill_screensaver()
                SCREENSAVER_ACTIVE = False

            time.sleep(CHECK_INTERVAL)
    finally:
        comtypes.CoUninitialize()

# ---------------------- Utility Functions ----------------------
def is_dark_mode():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return value == 0
    except Exception:
        return False

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ---------------------- Brightness Control Widget ----------------------
class BrightnessControl(QFrame):
    def __init__(self, tray_app):
        super().__init__()
        self.current_monitor = 0
        self.monitor_count = len(_monitors_cache)
        current_brightness = get_brightness(self.current_monitor)
        
        self.tray_app = tray_app
        self.setWindowTitle("Brightness Control")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setObjectName("BrightnessPopup")
        self.setStyleSheet("""
            #BrightnessPopup {
                border: 1px solid rgba(255, 255, 255, 0.1);
                background-color: #1e1e1e;
                color: white;
            }
        """)

        self.brightness_timer = QTimer()
        self.brightness_timer.setSingleShot(True)
        self.brightness_timer.setInterval(300)
        self.brightness_timer.timeout.connect(self.apply_slider_brightness)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        
        if self.monitor_count > 1:
            self.monitor_selector = QComboBox()
            for i in range(self.monitor_count):
                monitor_name = f"Monitor {i+1}"
                self.monitor_selector.addItem(monitor_name)
            self.monitor_selector.currentIndexChanged.connect(self.monitor_changed)
            main_layout.addWidget(self.monitor_selector)

        slider_layout = QHBoxLayout()

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(SETTINGS.get("slider_min", 1))
        self.slider.setMaximum(SETTINGS.get("slider_max", 100))
        self.slider.setValue(current_brightness)
        self.slider.valueChanged.connect(self.slider_changed)

        self.value_label = QLabel(str(current_brightness))
        self.value_label.setFixedWidth(30)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet("color: white;")

        slider_layout.addSpacing(10)
        slider_layout.addWidget(self.slider)
        slider_layout.addWidget(self.value_label)

        main_layout.addLayout(slider_layout)
        self.resize(230, 70 if self.monitor_count == 1 else 100)

    def monitor_changed(self, index):
        self.current_monitor = index
        self.sync_with_brightness()

    def slider_changed(self, value):
        self.value_label.setText(str(value))
        self.brightness_timer.start()

    def apply_slider_brightness(self):
        set_brightness(self.slider.value(), self.current_monitor)

    def sync_with_brightness(self):
        current = get_brightness(self.current_monitor)
        if current != self.slider.value():
            self.slider.blockSignals(True)
            self.slider.setValue(current)
            self.slider.blockSignals(False)
            self.value_label.setText(str(current))

    def showEvent(self, event):
        tray_click_pos = self.tray_app.last_tray_click_pos
        screen = QGuiApplication.screenAt(tray_click_pos)
        if screen:
            full_geom = screen.geometry()
            available_geom = screen.availableGeometry()
            popup_width = self.width()
            popup_height = self.height()

            x = min(max(tray_click_pos.x() - popup_width // 2, full_geom.left()),
                    full_geom.right() - popup_width)

            if tray_click_pos.y() > available_geom.bottom():
                y = available_geom.bottom() - popup_height - 8
            elif tray_click_pos.y() < available_geom.top():
                y = available_geom.top() + 8
            elif tray_click_pos.y() - popup_height - 10 >= available_geom.top():
                y = tray_click_pos.y() - popup_height - 10
            else:
                y = tray_click_pos.y() + 10

            self.move(QPoint(x, y))
        super().showEvent(event)

# ---------------------- Tray Application ----------------------
class TrayApp(QObject):
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        icon_path = "icon_light.png" if not is_dark_mode() else "icon_dark.png"
        self.tray_icon = QSystemTrayIcon(QIcon(resource_path(icon_path)))
        self.tray_icon.setToolTip("Brightness Manager")
        self.tray_icon.activated.connect(self.icon_clicked)

        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #333333;
                color: white;
                border: 1px solid #555;
                padding: 5px;
            }
            QMenu::item {
                padding: 5px 20px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #555555;
            }
            QMenu::separator {
                height: 1px;
                background: #555555;
                margin: 4px 0;
            }
            QMenu::item[text="Exit"] {
                text-align: center;
                color: #ff6b6b;
                font-weight: bold;
            }
        """)
        self.config_action = QAction("Config")
        self.config_action.triggered.connect(self.open_config)
        self.menu.addAction(self.config_action)
        self.quit_action = QAction("Exit")
        self.quit_action.triggered.connect(self.exit_app)
        self.menu.addAction(self.quit_action)

        self.tray_icon.setContextMenu(self.menu)
       
        self.tray_ui_enabled = TRAY_UI

        if self.tray_ui_enabled:
            self.tray_icon.show()
        else:
            self.tray_icon.hide()

        self.slider_widget = BrightnessControl(self)
        self.last_tray_click_pos = QPoint(0, 0)

    def icon_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context:
            self.show_menu()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.last_tray_click_pos = QCursor.pos()
            self.toggle_slider()

    def show_menu(self):
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos)
        if screen:
            screen_rect = screen.availableGeometry()
            menu_size = self.menu.sizeHint()

            x = min(cursor_pos.x(), screen_rect.right() - menu_size.width())
            y = min(cursor_pos.y(), screen_rect.bottom() - menu_size.height())

            self.menu.popup(QPoint(x, y))

    def toggle_slider(self):
        if self.slider_widget.isVisible():
            self.slider_widget.hide()
        else:
            self.slider_widget.sync_with_brightness()
            self.slider_widget.show()
    
    def open_config(self):
        try:
            os.startfile(SETTINGS_PATH)
        except Exception as e:
            print(f"Failed to open config: {e}")
    
    def exit_app(self):
        self.slider_widget.close()
        self.tray_icon.hide()
        os._exit(0)

    def run(self):
        self.app.exec()

# ---------------------- Run ----------------------
if __name__ == "__main__":
    threading.Thread(target=main_loop).start()
    TrayApp().run()
