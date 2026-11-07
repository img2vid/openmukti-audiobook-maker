from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkArea:
    x: int
    y: int
    width: int
    height: int


def fitted_size(screen_width: int, screen_height: int, desired_width: int, desired_height: int) -> tuple[int, int]:
    available_width = max(160, screen_width - min(48, max(12, screen_width // 20)))
    available_height = max(160, screen_height - min(115, max(100, screen_height // 7)))
    return min(desired_width, available_width), min(desired_height, available_height)


def fitted_geometry(screen_width: int, screen_height: int, desired_width: int, desired_height: int) -> str:
    width, height = fitted_size(screen_width, screen_height, desired_width, desired_height)
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2 - min(12, screen_height // 45))
    return f'{width}x{height}+{x}+{y}'


def _windows_work_area(window) -> WorkArea | None:
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class Rect(ctypes.Structure):
            _fields_ = [('left', wintypes.LONG), ('top', wintypes.LONG), ('right', wintypes.LONG), ('bottom', wintypes.LONG)]

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', Rect), ('rcWork', Rect), ('dwFlags', wintypes.DWORD)]

        user32 = ctypes.windll.user32
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        monitor = user32.MonitorFromWindow(window.winfo_id(), 2)
        if not monitor:
            return None
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(MonitorInfo)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        monitor_width = info.rcMonitor.right - info.rcMonitor.left
        monitor_height = info.rcMonitor.bottom - info.rcMonitor.top
        primary_native_width = user32.GetSystemMetrics(0)
        primary_native_height = user32.GetSystemMetrics(1)
        tk_width = max(1, window.winfo_screenwidth())
        tk_height = max(1, window.winfo_screenheight())
        scale_x = primary_native_width / tk_width if primary_native_width else 1
        scale_y = primary_native_height / tk_height if primary_native_height else 1
        if not (0.5 <= scale_x <= 4):
            scale_x = 1
        if not (0.5 <= scale_y <= 4):
            scale_y = 1
        left = round(info.rcWork.left / scale_x)
        top = round(info.rcWork.top / scale_y)
        width = round((info.rcWork.right - info.rcWork.left) / scale_x)
        height = round((info.rcWork.bottom - info.rcWork.top) / scale_y)
        if monitor_width <= 0 or monitor_height <= 0 or width <= 0 or height <= 0:
            return None
        return WorkArea(left, top, width, height)
    except (OSError, AttributeError, ValueError, TypeError):
        return None


def work_area(window) -> WorkArea:
    native = _windows_work_area(window)
    if native is not None:
        return native
    return WorkArea(0, 0, max(160, window.winfo_screenwidth()), max(160, window.winfo_screenheight()))


def bounded_geometry(area: WorkArea, x: int, y: int, width: int, height: int) -> str:
    width = min(max(160, width), area.width)
    height = min(max(160, height), area.height)
    x = max(area.x, min(x, area.x + area.width - width))
    y = max(area.y, min(y, area.y + area.height - height))
    return f'{width}x{height}{x:+d}{y:+d}'


def fit_window(window, desired_width: int, desired_height: int, minimum_width: int = 480, minimum_height: int = 360) -> None:
    area = work_area(window)
    width, height = fitted_size(area.width, area.height, desired_width, desired_height)
    window.minsize(min(width, minimum_width), min(height, minimum_height))
    vertical = max(0, (area.height - height - (50 if os.name == 'nt' else 70)) // 2)
    window.geometry(bounded_geometry(area, area.x + (area.width-width)//2, area.y + vertical, width, height))
    window.resizable(True, True)


def keep_window_visible(window) -> None:
    try:
        if not window.winfo_exists() or window.attributes('-fullscreen'):
            return
        area = work_area(window)
        width, height = max(160, window.winfo_width()), max(160, window.winfo_height())
        x, y = window.winfo_x(), window.winfo_y()
        try:
            frame_extra = max(0, window.winfo_rooty() - y)
        except Exception:
            frame_extra = 0
        effective_bottom = area.y + area.height - min(90, frame_extra)
        window.minsize(min(480, area.width), min(330, area.height))
        if str(window.state()) in ('zoomed', 'iconic', 'withdrawn'):
            return
        adjusted = WorkArea(area.x, area.y, area.width, max(160, effective_bottom - area.y))
        target = bounded_geometry(adjusted, x, y, width, height)
        if (width > adjusted.width or height > adjusted.height or x < adjusted.x or y < adjusted.y or x + width > adjusted.x + adjusted.width or y + height > adjusted.y + adjusted.height):
            window.geometry(target)
    except Exception:
        return


def scrollable_area(parent, *, padding: int = 12, background: str = '#111827', panel_style: str = 'TFrame'):
    import tkinter as tk
    from tkinter import ttk

    shell = ttk.Frame(parent)
    canvas = tk.Canvas(shell, bg=background, bd=0, highlightthickness=0, yscrollincrement=14)
    scrollbar = ttk.Scrollbar(shell, orient='vertical', command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')
    panel = ttk.Frame(canvas, style=panel_style, padding=padding)
    item = canvas.create_window((0, 0), window=panel, anchor='nw')

    def content_changed(_event=None):
        canvas.configure(scrollregion=canvas.bbox('all'))

    def viewport_changed(event):
        canvas.itemconfigure(item, width=max(1, event.width))
        content_changed()

    panel.bind('<Configure>', content_changed)
    canvas.bind('<Configure>', viewport_changed)

    # Bind each top-level window only once.  Previously every nested scroll
    # panel registered a new top-level Tcl callback, then unbound that callback
    # synchronously from a child <Destroy> event.  FormEditor.reset() destroys
    # and recreates those children several times, and changing Tk bindings
    # while Tk is dispatching destruction can crash native Tcl/Tk on macOS.
    #
    # The registry only holds live scroll areas.  Destruction removes a record
    # without changing a Tcl event binding; the single dispatcher is released
    # automatically when its owning top-level window is destroyed.
    top = parent.winfo_toplevel()
    targets = getattr(top, '_openmukti_scroll_targets', None)
    if targets is None:
        targets = []
        top._openmukti_scroll_targets = targets

        def wheel(event):
            try:
                widget = event.widget
                if widget.winfo_toplevel() is not top:
                    return
                if widget.winfo_class() in ('Text', 'Treeview', 'Listbox', 'TCombobox'):
                    return
                if getattr(event, 'num', None) in (4, 5):
                    delta = -3 if event.num == 4 else 3
                elif getattr(event, 'delta', 0):
                    delta = -3 if event.delta > 0 else 3
                else:
                    return
                # Check innermost panels first, for nested scrollable editors.
                for candidate, target_canvas in reversed(tuple(targets)):
                    ancestor = widget
                    while ancestor is not None and ancestor is not candidate:
                        ancestor = getattr(ancestor, 'master', None)
                    if ancestor is not candidate:
                        continue
                    if not target_canvas.winfo_exists() or not target_canvas.winfo_viewable():
                        return
                    target_canvas.yview_scroll(delta, 'units')
                    return 'break'
            except tk.TclError:
                # Tk may dispatch a final event while a window is being closed.
                return

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            top.bind(sequence, wheel, add='+')

    targets.append((shell, canvas))

    def cleanup(event):
        if event.widget is shell:
            targets[:] = [record for record in targets if record[0] is not shell]

    shell.bind('<Destroy>', cleanup, add='+')
    return shell, panel, canvas


def adaptive_grid(parent, buttons, columns: int = 2, *, padx: int = 3, pady: int = 3):
    from tkinter import ttk
    for col in range(columns):
        parent.columnconfigure(col, weight=1)
    result = []
    for i, (label, callback) in enumerate(buttons):
        button = ttk.Button(parent, text=label, command=callback)
        button.grid(row=i // columns, column=i % columns, sticky='ew', padx=padx, pady=pady)
        result.append(button)
    return result


def prepare_desktop_dpi():
    """Ask Windows for physical per-monitor coordinates before a Tk window exists."""
    if os.name!='nt':
        return
    import ctypes
    try:
        fn=ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.argtypes=[ctypes.c_void_p]
        fn.restype=ctypes.c_int
        if fn(ctypes.c_void_p(-4)):
            return
    except (AttributeError,OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError,OSError):
        pass


def scale_factor(dpi,percent):
    if not 50<=percent<=300:
        raise ValueError('Interface scale must be 50–300 percent')
    return min(8,max(.5,(dpi/72)*(percent/100)))


def apply_display_scale(root,percent=100):
    if not hasattr(root,'_initial_tk_dpi'):
        root._initial_tk_dpi=float(root.tk.call('tk','scaling'))*72
    dpi=root._initial_tk_dpi
    if os.name=='nt':
        try:
            import ctypes
            fn=ctypes.windll.user32.GetDpiForWindow
            fn.argtypes=[ctypes.c_void_p]
            fn.restype=ctypes.c_uint
            dpi=fn(root.winfo_id()) or dpi
        except (AttributeError,OSError):
            pass
    value=scale_factor(dpi,percent)
    if abs(float(root.tk.call('tk','scaling'))-value)>.025:
        root.tk.call('tk','scaling',value)
    return value
