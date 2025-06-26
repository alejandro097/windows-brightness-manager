# Windows Brightness Manager (WIP V1.0)

A lightweight Python application for Windows that automatically dims and restores monitor brightness based on system idle time and media playback status. Supports multiple monitors with independent brightness controls through a system tray interface.

Only DDC/CI-compatible monitor(s)

## Features

- Auto-dim monitors after user inactivity (configurable timeout)
- Delay dimming if media (audio/video) is playing
- Restore brightness automatically on activity or media playback
- Multi-monitor support with individual brightness settings
- Tray icon with a popup slider for manual brightness control per monitor
- Configurable via a JSON settings file

## Installation

You can either run the app from source using Python, or download a precompiled executable.

##  Download

You can download the latest version of **Windows Brightness Manager** here:

[Download for Windows (zip)](https://files.catbox.moe/90vcir.zip)

Make sure to extract the `.zip` file before running the app.


##  How to Use

1. Download and extract the `.zip` file.
2. Double-click `wbmanager.exe` to launch the brightness manager.
3. App runs in the system tray.

##  How to compile it

1. Clone the repository:

   git clone https://github.com/yourusername/windows-brightness-manager.git

   cd windows-brightness-manager

2. Install python then run

   pip install PySide6 monitorcontrol pycaw comtypes

3. Run the application.
   
   python main.py
   
