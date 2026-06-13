# gnome-display-setup

Configure displays on GNOME Wayland via the Mutter DBus API. Works where `xrandr` does not.

## Requirements

```bash
sudo apt install python3-gi
```

`python3-gi` is usually pre-installed on Ubuntu GNOME.

## Usage

```bash
python3 set_displays.py               # external display above laptop (default)
python3 set_displays.py --below       # external display below laptop
python3 set_displays.py --mirror      # mirror all displays
python3 set_displays.py --laptop-only # disable all external displays
python3 set_displays.py --list        # list connected displays and modes
```

## How it works

GNOME on Wayland ignores `xrandr` — display configuration must go through `org.gnome.Mutter.DisplayConfig` over DBus. This script calls `GetCurrentState` to auto-detect connected monitors, then applies the chosen layout via `ApplyMonitorsConfig` with method `2` (persistent across sessions).

External monitors are detected automatically by connector name and display name, so it works with any TV or monitor on any port without hardcoding.
