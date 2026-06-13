#!/usr/bin/env python3
"""
Configure displays via GNOME Mutter DBus (Wayland-compatible).

Usage:
  set_displays.py               # external above laptop (default)
  set_displays.py --below       # external below laptop
  set_displays.py --mirror      # mirror all displays
  set_displays.py --laptop-only # disable all external displays
  set_displays.py --list        # list connected displays and modes
"""

import argparse
import dbus


def get_display_config():
    bus = dbus.SessionBus()
    proxy = bus.get_object("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig")
    iface = dbus.Interface(proxy, "org.gnome.Mutter.DisplayConfig")
    serial, monitors, logical_monitors, props = iface.GetCurrentState()
    return iface, serial, monitors


def best_1080p_mode(modes):
    """Return the mode ID closest to 1920x1080 at the highest refresh rate."""
    candidates = [(str(m[0]), int(m[1]), int(m[2]), float(m[3])) for m in modes]
    # Prefer exact 1920x1080, then highest res, then highest refresh
    def score(m):
        mid, w, h, hz = m
        exact = (w == 1920 and h == 1080)
        return (exact, w * h, hz)
    return max(candidates, key=score)[0]


def parse_monitors(monitors):
    """Return list of dicts with connector, display_name, is_builtin, best_mode."""
    result = []
    for spec, modes, props in monitors:
        connector = str(spec[0])
        is_builtin = bool(props.get("is-builtin", False))
        display_name = str(props.get("display-name", connector))
        mode = best_1080p_mode(modes)
        result.append({
            "connector": connector,
            "display_name": display_name,
            "is_builtin": is_builtin,
            "mode": mode,
        })
    return result


def make_monitor_entry(connector, mode):
    return (connector, mode, dbus.Dictionary({}, signature="sv"))


def apply_config(iface, serial, logical_monitors):
    iface.ApplyMonitorsConfig(
        serial,
        dbus.UInt32(2),  # 2 = persistent
        logical_monitors,
        dbus.Dictionary({}, signature="sv"),
    )


def cmd_list(monitors):
    for m in monitors:
        tag = " [built-in]" if m["is_builtin"] else ""
        print(f"  {m['connector']}{tag}  —  {m['display_name']}  (best mode: {m['mode']})")


def cmd_mirror(iface, serial, monitors):
    # All displays at (0,0) with the same mode — use the laptop's mode as common ground
    builtin = next((m for m in monitors if m["is_builtin"]), monitors[0])
    common_mode = builtin["mode"]
    logical = []
    for i, m in enumerate(monitors):
        logical.append((
            dbus.Int32(0), dbus.Int32(0), dbus.Double(1.0), dbus.UInt32(0),
            dbus.Boolean(m["is_builtin"]),
            [make_monitor_entry(m["connector"], common_mode)],
        ))
    apply_config(iface, serial, logical)
    print(f"Mirroring {len(monitors)} display(s) at {common_mode}.")


def cmd_stack(iface, serial, monitors, external_above=True):
    builtin = next((m for m in monitors if m["is_builtin"]), None)
    externals = [m for m in monitors if not m["is_builtin"]]

    if not builtin:
        print("No built-in display found.")
        return
    if not externals:
        print("No external display connected — nothing to stack.")
        return

    # Stack externals side-by-side above (or below) the laptop
    logical = []
    ext_x = 0
    ext_height = 1080  # assume all externals at 1080 height for offset calc

    for ext in externals:
        y = 0 if external_above else ext_height
        logical.append((
            dbus.Int32(ext_x), dbus.Int32(y), dbus.Double(1.0), dbus.UInt32(0),
            dbus.Boolean(False),
            [make_monitor_entry(ext["connector"], ext["mode"])],
        ))
        # Extract width from mode string e.g. "1920x1080@60.000"
        try:
            ext_x += int(ext["mode"].split("x")[0])
        except (ValueError, IndexError):
            ext_x += 1920

    laptop_y = ext_height if external_above else 0
    logical.append((
        dbus.Int32(0), dbus.Int32(laptop_y), dbus.Double(1.0), dbus.UInt32(0),
        dbus.Boolean(True),
        [make_monitor_entry(builtin["connector"], builtin["mode"])],
    ))

    apply_config(iface, serial, logical)
    pos = "above" if external_above else "below"
    ext_names = ", ".join(e["connector"] for e in externals)
    print(f"Applied: {ext_names} {pos} {builtin['connector']} (primary).")


def cmd_laptop_only(iface, serial, monitors):
    builtin = next((m for m in monitors if m["is_builtin"]), None)
    if not builtin:
        print("No built-in display found.")
        return
    logical = [(
        dbus.Int32(0), dbus.Int32(0), dbus.Double(1.0), dbus.UInt32(0),
        dbus.Boolean(True),
        [make_monitor_entry(builtin["connector"], builtin["mode"])],
    )]
    apply_config(iface, serial, logical)
    print(f"Laptop-only: {builtin['connector']} at {builtin['mode']}.")


def main():
    parser = argparse.ArgumentParser(description="Configure GNOME displays (Wayland).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mirror", action="store_true", help="Mirror all displays")
    group.add_argument("--below", action="store_true", help="External display below laptop")
    group.add_argument("--laptop-only", action="store_true", help="Disable all external displays")
    group.add_argument("--list", action="store_true", help="List connected displays")
    args = parser.parse_args()

    iface, serial, raw_monitors = get_display_config()
    monitors = parse_monitors(raw_monitors)

    if not monitors:
        print("No displays found.")
        return

    if args.list:
        cmd_list(monitors)
    elif args.mirror:
        cmd_mirror(iface, serial, monitors)
    elif args.laptop_only:
        cmd_laptop_only(iface, serial, monitors)
    else:
        # Default and --below
        cmd_stack(iface, serial, monitors, external_above=not args.below)


if __name__ == "__main__":
    main()
