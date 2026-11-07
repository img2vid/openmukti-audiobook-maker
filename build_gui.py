"""Graphical host-native build launcher using the existing supported builders."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


def build_command(formats, profile='auto', *, auto_dependencies=True, plan_only=False, repair=False):
    from build_select import host_formats, selected_profile
    if not formats or any(f not in host_formats() for f in formats):
        raise ValueError('Choose at least one package available for this computer.')
    args = [sys.executable, '-u', str(Path(__file__).with_name('build.py')), '--formats', ','.join(formats), '--profile', selected_profile(profile)]
    if not auto_dependencies:
        args.append('--no-auto-deps')
    if plan_only:
        args.append('--deps-plan')
    if repair:
        args.append('--repair')
    return args


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk, font
    from build_select import LABELS, host_formats
    from scripts.platform_support import system, architecture
    from openvoice.windowing import fit_window, scrollable_area

    root = tk.Tk()
    root.title('Openmukti · Build application')
    fit_window(root, 850, 720, 440, 360)
    ttk.Style(root).theme_use('clam')
    ttk.Label(root, text='Build Openmukti for this computer', font=(font.nametofont('TkDefaultFont',root=root).actual()['family'], 18, 'bold')).pack(anchor='w', padx=16, pady=(14, 5))
    ttk.Label(root, text=f'Computer: {system().capitalize()} / {architecture()}').pack(anchor='w', padx=16)
    ttk.Label(root, text='Choose package formats below. Native platform tools may be needed for the selected package.', wraplength=760).pack(anchor='w', padx=16, pady=6)
    shell, panel, _ = scrollable_area(root, background='#d9d9d9')
    shell.pack(fill='both', expand=True, padx=8)
    formats = host_formats()
    chosen = {}
    for i, name in enumerate(formats):
        var = tk.BooleanVar(root, value=i == 0)
        chosen[name] = var
        ttk.Checkbutton(panel, text=LABELS.get(name, name), variable=var).pack(anchor='w', pady=3)
    controls = ttk.Frame(root, padding=12)
    controls.pack(fill='x')
    profile = tk.StringVar(root, value='Automatic')
    ttk.Label(controls, text='Application package').grid(row=0, column=0, sticky='w', padx=(0, 8))
    ttk.Combobox(controls, textvariable=profile, state='readonly', values=['Automatic', 'Include Python and dependencies', 'Use installed Python']).grid(row=0, column=1, sticky='ew')
    automatic = tk.BooleanVar(root, value=True)
    repair = tk.BooleanVar(root, value=False)
    ttk.Checkbutton(controls, text='Install required build dependencies automatically', variable=automatic).grid(row=1, column=0, columnspan=2, sticky='w', pady=5)
    if system() == 'windows':
        ttk.Checkbutton(controls, text='Repair / resume the previous Windows build', variable=repair).grid(row=2, column=0, columnspan=2, sticky='w')
    controls.columnconfigure(1, weight=1)
    status = tk.StringVar(root, value='Ready. Build packages are saved in the dist folder.')
    ttk.Label(root, textvariable=status, wraplength=760).pack(fill='x', padx=16, pady=5)
    progress = ttk.Progressbar(root, mode='indeterminate')
    progress.pack(fill='x', padx=16)
    logs = tk.Text(root, height=10, wrap='word', state='disabled')
    logs.pack(fill='both', expand=True, padx=16, pady=8)
    events = queue.Queue()
    state = {'process': None, 'running': False, 'plan': False}

    def append(text):
        logs.configure(state='normal')
        logs.insert('end', text)
        logs.see('end')
        logs.configure(state='disabled')

    def start(plan=False):
        if state['running']:
            return
        try:
            args = build_command([f for f, v in chosen.items() if v.get()],
                {'Automatic': 'auto', 'Include Python and dependencies': 'frozen', 'Use installed Python': 'system'}[profile.get()],
                auto_dependencies=automatic.get(), plan_only=plan, repair=repair.get())
        except ValueError as exc:
            messagebox.showerror('Choose packages', str(exc), parent=root)
            return
        state.update(running=True,plan=plan)
        build_button.state(['disabled'])
        plan_button.state(['disabled'])
        status.set('Checking build requirements…' if plan else 'Building application packages…')
        progress.start(12)
        append('\nChecking requirements…\n' if plan else '\nStarting build…\n')
        def work():
            try:
                proc = subprocess.Popen(args, cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
                    start_new_session=os.name!='nt', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                state['process'] = proc
                for text in proc.stdout:
                    events.put(('text', text))
                events.put(('done', proc.wait()))
            except Exception as exc:
                events.put(('text', str(exc) + '\n'))
                events.put(('done', 1))
        threading.Thread(target=work, daemon=True).start()

    def stop():
        proc = state['process']
        if proc and proc.poll() is None:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                import signal
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            status.set('Stopping the build…')

    def poll():
        try:
            for _ in range(200):
                kind, value = events.get_nowait()
                if kind == 'text':
                    append(value)
                else:
                    state.update(running=False, process=None)
                    progress.stop()
                    build_button.state(['!disabled'])
                    plan_button.state(['!disabled'])
                    status.set(('Requirements check finished. Review the details above.' if state['plan'] else 'Finished. See the details above and the dist folder.') if value == 0 else 'Build stopped or failed. The details above explain the issue.')
        except queue.Empty:
            pass
        root.after(100, poll)

    def save_log():
        name = filedialog.asksaveasfilename(parent=root, defaultextension='.txt', initialfile='build-report.txt')
        if name:
            Path(name).write_text(logs.get('1.0', 'end-1c'), encoding='utf-8')

    def outputs():
        folder = Path(__file__).parent / 'dist'
        folder.mkdir(exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(folder)])
        else:
            subprocess.Popen(['xdg-open', str(folder)])

    footer = ttk.Frame(root, padding=12)
    footer.pack(fill='x')
    build_button = ttk.Button(footer, text='Build selected packages', command=start)
    build_button.pack(side='left', padx=3)
    plan_button = ttk.Button(footer, text='Check requirements', command=lambda: start(True))
    plan_button.pack(side='left', padx=3)
    for title, cmd in [('Stop', stop), ('Open outputs', outputs), ('Save log', save_log)]:
        ttk.Button(footer, text=title, command=cmd).pack(side='left', padx=3)

    def close():
        if state['running']:
            messagebox.showinfo('Build is running', 'Stop the build and wait for it to finish before closing.', parent=root)
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(100, poll)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
