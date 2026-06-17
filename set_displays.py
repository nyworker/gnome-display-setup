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
from gi.repository import Gio, GLib


def get_proxy():
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.NONE,
        None,
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        None,
    )


def get_display_config(proxy):
    result = proxy.call_sync("GetCurrentState", None, Gio.DBusCallFlags.NONE, -1, None)
    serial, monitors, logical_monitors, props = result.unpack()
    return serial, monitors


def best_1080p_mode(modes):
    """Return the mode ID closest to 1920x1080 at the highest refresh rate."""
    def score(m):
        w, h, hz = m[1], m[2], m[3]
        return (w == 1920 and h == 1080, w * h, hz)
    return max(modes, key=score)[0]


def best_native_mode(modes):
    """Return the mode ID with the highest resolution and refresh rate (native)."""
    return max(modes, key=lambda m: (m[1] * m[2], m[3]))[0]


def parse_monitors(monitors):
    result = []
    for spec, modes, props in monitors:
        connector = spec[0]
        is_builtin = bool(props.get("is-builtin", False))
        display_name = str(props.get("display-name", connector))
        mode = best_1080p_mode(modes)
        # Store all modes as {(width, height): mode_id} for mirror resolution matching
        modes_by_res = {}
        for m in modes:
            modes_by_res[(m[1], m[2])] = modes_by_res.get((m[1], m[2])) or m[0]
        result.append({
            "connector": connector,
            "display_name": display_name,
            "is_builtin": is_builtin,
            "mode": mode,
            "native_mode": best_native_mode(modes),
            "modes_by_res": modes_by_res,
        })
    return result


def apply_config(proxy, serial, logical_monitors):
    # a(iiduba(ssa{sv}))  — each logical monitor: x, y, scale, transform, primary, [monitors]
    params = GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 2, logical_monitors, {}))
    proxy.call_sync("ApplyMonitorsConfig", params, Gio.DBusCallFlags.NONE, -1, None)


def lm(x, y, primary, monitors):
    """Build a logical monitor tuple."""
    return (x, y, 1.0, 0, primary, [(m["connector"], m["mode"], {}) for m in monitors])


def cmd_list(monitors):
    for m in monitors:
        tag = " [built-in]" if m["is_builtin"] else ""
        print(f"  {m['connector']}{tag}  —  {m['display_name']}  (best mode: {m['mode']})")


def cmd_mirror(proxy, serial, monitors):
    # Find the highest resolution supported by all displays
    common_res = set.intersection(*[set(m["modes_by_res"]) for m in monitors])
    if not common_res:
        print("No common resolution found across all displays.")
        return
    w, h = max(common_res, key=lambda r: (r[0] * r[1]))

    # All physical monitors go in a single logical monitor — that's how Mutter mirrors them
    monitor_entries = [(m["connector"], m["modes_by_res"][(w, h)], {}) for m in monitors]
    logical = [(0, 0, 1.0, 0, True, monitor_entries)]
    apply_config(proxy, serial, logical)
    print(f"Mirroring {len(monitors)} display(s) at {w}x{h}.")


def cmd_stack(proxy, serial, monitors, external_above=True):
    builtin = next((m for m in monitors if m["is_builtin"]), None)
    externals = [m for m in monitors if not m["is_builtin"]]

    if not builtin:
        print("No built-in display found.")
        return
    if not externals:
        print("No external display connected — nothing to stack.")
        return

    ext_height = 1080
    logical = []
    ext_x = 0
    for ext in externals:
        y = 0 if external_above else ext_height
        logical.append(lm(ext_x, y, False, [ext]))
        try:
            ext_x += int(ext["mode"].split("x")[0])
        except (ValueError, IndexError):
            ext_x += 1920

    laptop_y = ext_height if external_above else 0
    logical.append(lm(0, laptop_y, True, [builtin]))

    apply_config(proxy, serial, logical)
    pos = "above" if external_above else "below"
    print(f"Applied: {', '.join(e['connector'] for e in externals)} {pos} {builtin['connector']} (primary).")


def cmd_laptop_only(proxy, serial, monitors):
    builtin = next((m for m in monitors if m["is_builtin"]), None)
    if not builtin:
        print("No built-in display found.")
        return
    builtin = {**builtin, "mode": builtin["native_mode"]}
    apply_config(proxy, serial, [lm(0, 0, True, [builtin])])
    print(f"Laptop-only: {builtin['connector']} at {builtin['mode']}.")


def main():
    parser = argparse.ArgumentParser(description="Configure GNOME displays (Wayland).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mirror", action="store_true", help="Mirror all displays")
    group.add_argument("--below", action="store_true", help="External display below laptop")
    group.add_argument("--laptop-only", action="store_true", help="Disable all external displays")
    group.add_argument("--list", action="store_true", help="List connected displays")
    args = parser.parse_args()

    proxy = get_proxy()
    serial, raw_monitors = get_display_config(proxy)
    monitors = parse_monitors(raw_monitors)

    if not monitors:
        print("No displays found.")
        return

    if args.list:
        cmd_list(monitors)
    elif args.mirror:
        cmd_mirror(proxy, serial, monitors)
    elif args.laptop_only:
        cmd_laptop_only(proxy, serial, monitors)
    else:
        cmd_stack(proxy, serial, monitors, external_above=not args.below)


if __name__ == "__main__":
    main()
