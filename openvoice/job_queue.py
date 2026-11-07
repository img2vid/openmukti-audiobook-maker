"""Durable render queue. Only registered local production commands can be enqueued."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

ALLOWED = {'render', 'video', 'audiobooks', 'project-render', 'multivoice', 'batch'}
SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, arguments TEXT NOT NULL, cwd TEXT NOT NULL, priority INTEGER,
    ready REAL, state TEXT, token TEXT, heartbeat REAL, error TEXT, progress_log TEXT, output_key TEXT)"""


@contextmanager
def connection(db):
    path = Path(db).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=30)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute(SCHEMA)
        if 'output_key' not in {row[1] for row in conn.execute('PRAGMA table_info(jobs)')}:
            try:
                conn.execute('ALTER TABLE jobs ADD COLUMN output_key TEXT')
            except sqlite3.OperationalError:
                if 'output_key' not in {r[1] for r in conn.execute('PRAGMA table_info(jobs)')}:
                    raise
        yield conn


def enqueue(db, argv, priority=0, ready=0, cwd=None):
    if not argv or argv[0] not in ALLOWED:
        raise ValueError('Queue accepts production commands: ' + ', '.join(sorted(ALLOWED)))
    cwd = Path(cwd or os.getcwd()).resolve(strict=True)
    out=next((argv[i+1] for i,v in enumerate(argv[:-1]) if v in ('-w','--output','--output-dir')),None)
    key=os.path.normcase(str((cwd/out).resolve())) if out else json.dumps([str(cwd),argv],sort_keys=True)
    with connection(db) as conn:
        row = conn.execute("INSERT INTO jobs(arguments,cwd,priority,ready,state,output_key) VALUES (?,?,?,?,'pending',?)",
                           (json.dumps(argv), str(cwd), int(priority), float(ready),key))
        return row.lastrowid


def jobs(db):
    with connection(db) as conn:
        return [dict(row) for row in conn.execute(
            'SELECT id,arguments,cwd,priority,ready,state,error,progress_log FROM jobs ORDER BY priority DESC,id')]


def modify(db, job_id, action, value=0):
    with connection(db) as conn:
        if action == 'cancel':
            cur = conn.execute("UPDATE jobs SET state='cancelled' WHERE id=? AND state IN ('pending','running')", (job_id,))
        elif action == 'retry':
            cur = conn.execute("UPDATE jobs SET state='pending',token=NULL,error=NULL,ready=0 WHERE id=? AND state IN ('failed','cancelled')", (job_id,))
        elif action == 'priority':
            cur = conn.execute("UPDATE jobs SET priority=? WHERE id=? AND state='pending'", (value, job_id))
        else:
            raise ValueError('Unknown queue operation')
        if cur.rowcount != 1:
            raise ValueError('Job does not exist or is in the wrong state')


def claim(db):
    now = time.time()
    with connection(db) as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("UPDATE jobs SET state='pending',token=NULL WHERE state='running' AND heartbeat<?", (now-180,))
        row = conn.execute("SELECT * FROM jobs WHERE state='pending' AND ready<=? AND NOT EXISTS (SELECT 1 FROM jobs busy WHERE busy.state='running' AND busy.output_key=jobs.output_key) ORDER BY priority DESC,id LIMIT 1", (now,)).fetchone()
        if row is None:
            return None
        token = uuid.uuid4().hex
        conn.execute("UPDATE jobs SET state='running',token=?,heartbeat=? WHERE id=?", (token, now, row['id']))
        return dict(row), token


def resource_hold(folder, *, min_disk_mb=0, min_memory_mb=0, max_temp=0, min_battery=0):
    if shutil.disk_usage(folder).free < min_disk_mb * 1048576:
        return 'free disk space'
    if any((min_memory_mb, max_temp, min_battery)):
        try:
            import psutil
        except ImportError as exc:
            raise RuntimeError('Install psutil for battery, temperature or available-memory rules') from exc
        if min_memory_mb and psutil.virtual_memory().available < min_memory_mb * 1048576:
            return 'available memory'
        if max_temp:
            sensors = getattr(psutil, 'sensors_temperatures', lambda: {})()
            if any(s.current is not None and s.current >= max_temp for group in sensors.values() for s in group):
                return 'temperature'
        if min_battery:
            battery = getattr(psutil, 'sensors_battery', lambda: None)()
            if battery and not battery.power_plugged and battery.percent < min_battery:
                return 'battery charge'
    return ''


def cli_process():
    env=dict(os.environ)
    if not getattr(sys,'frozen',False):
        env['PYTHONPATH']=os.pathsep.join(filter(None,[str(Path(__file__).resolve().parent.parent),env.get('PYTHONPATH')]))
        return [sys.executable,'-m','openvoice'],env
    exe=Path(sys.executable)
    if 'cmd' not in exe.stem.casefold() and 'cli' not in exe.stem.casefold():
        names=['OpenmuktiAudiobookMakerCMD'+exe.suffix,'openvoice-cli'+exe.suffix]
        exe=next((exe.parent/name for name in names if (exe.parent/name).is_file()),None)
        if exe is None:
            raise RuntimeError('Place the companion command-line executable beside the desktop app')
    return [str(exe)],env


def worker(db, *, follow=False, profile='balanced', timeout=0, idle_timeout=0, max_process_mb=0, energy_saving=False, **limits):
    from .hardware import PROFILES
    if profile not in PROFILES or min(timeout,idle_timeout,max_process_mb) < 0 or any(value < 0 for value in limits.values()):
        raise ValueError('Invalid performance profile or resource limit')
    folder = Path(db).expanduser().resolve().parent
    folder.mkdir(parents=True, exist_ok=True)
    support=None
    if max_process_mb or energy_saving or any(limits.get(k) for k in ('max_temp','min_battery','min_memory_mb')):
        try:
            import psutil as support
        except ImportError:
            raise RuntimeError('Install psutil for active process resource controls')
    failures = 0
    while True:
        hold = resource_hold(folder, **limits)
        record = None if hold else claim(db)
        if not record:
            if not follow:
                if hold:
                    raise RuntimeError('Queue paused for ' + hold)
                return failures
            time.sleep(2)
            continue
        job, token = record
        log = folder / f'job-{job["id"]}-{token[:8]}.log'
        cmd,env=cli_process()
        env['OPENMUKTI_RENDER_CACHE']=str(folder/'speech-cache')
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[name] = str(PROFILES[profile]['threads'])
        argv = json.loads(job['arguments'])
        if not argv or argv[0] not in ALLOWED:
            raise ValueError('Unsupported queued command')
        proc = None
        start = time.monotonic()
        state, error = 'failed', ''
        try:
            with log.open('wb') as stream:
                proc = subprocess.Popen(cmd + argv, cwd=job['cwd'], env=env, start_new_session=(os.name!='nt'),
                                        stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
                paused=[]
                last_change=start
                last_size=0
                if energy_saving and support:
                    try:
                        support.Process(proc.pid).nice(support.BELOW_NORMAL_PRIORITY_CLASS if os.name=='nt' else 10)
                    except support.Error:
                        pass
                while proc.poll() is None:
                    with connection(db) as conn:
                        keep = conn.execute("UPDATE jobs SET heartbeat=?, progress_log=? WHERE id=? AND token=? AND state='running'",
                                            (time.time(), str(log), job['id'], token)).rowcount
                    if not keep:
                        break
                    if support:
                        try:
                            parent=support.Process(proc.pid)
                            tree=[parent,*parent.children(recursive=True)]
                            if max_process_mb and sum(p.memory_info().rss for p in tree)>max_process_mb*1048576:
                                raise RuntimeError('Process tree exceeded the configured memory budget')
                            reason=resource_hold(folder,**limits)
                            if reason and not paused:
                                for p in tree:
                                    try:
                                        p.suspend()
                                        paused.append(p)
                                    except support.Error:
                                        pass
                            elif not reason and paused:
                                for p in reversed(paused):
                                    try:
                                        p.resume()
                                    except support.Error:
                                        pass
                                paused=[]
                            if paused:
                                last_change=time.monotonic()
                                time.sleep(.7)
                                continue
                        except support.NoSuchProcess:
                            pass
                    size=log.stat().st_size
                    if size!=last_size:
                        last_change=time.monotonic()
                        last_size=size
                    if idle_timeout and time.monotonic()-last_change>idle_timeout:
                        raise RuntimeError('No production output within the configured stall interval')
                    if timeout and time.monotonic()-start > timeout:
                        raise RuntimeError('Job exceeded its configured watchdog timeout')
                    try:
                        proc.wait(timeout=.75)
                    except subprocess.TimeoutExpired:
                        pass
                if proc.poll() == 0:
                    state = 'done'
                elif proc.poll() is not None:
                    error = f'Process exited with code {proc.returncode}'
        except (OSError, RuntimeError) as exc:
            error = str(exc)
        finally:
            if proc and proc.poll() is None:
                if os.name!='nt':
                    import signal
                    try:
                        os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    subprocess.run(['taskkill','/T','/F','/PID',str(proc.pid)],capture_output=True,check=False)
                    if proc.poll() is None:
                        proc.kill()
                proc.wait()
            with connection(db) as conn:
                done = conn.execute("UPDATE jobs SET state=?,error=?,progress_log=? WHERE id=? AND token=? AND state='running'",
                                    (state, error, str(log), job['id'], token)).rowcount
        failures += int(bool(done) and state == 'failed')
