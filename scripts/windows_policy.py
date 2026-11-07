"""Report Windows execution-policy blocks without changing the policy."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from pathlib import Path

POLICY_EXIT_CODE = 3
POLICY_ERRORS = {4551, 1260}
PROGRAMS = ('OpenmuktiAudiobookMaker.exe', 'OpenmuktiAudiobookMakerCMD.exe')


class WindowsPolicyBlocked(RuntimeError):
    def __init__(self, command, error):
        self.command = tuple(str(x) for x in command)
        self.winerror = getattr(error, 'winerror', None)
        self.blocked_file = self.command[0] if self.command else ''
        super().__init__(f'Windows application policy blocked {self.blocked_file} (WinError {self.winerror}). The executable requires policy approval or appropriate trusted code signing before it can run.')


def is_policy_block(error):
    return getattr(error, 'winerror', None) in POLICY_ERRORS


def inventory(folder):
    outputs = []
    for name in PROGRAMS:
        path = Path(folder) / name
        item = {'name': name, 'path': str(path), 'exists': path.is_file(), 'pe_header': False}
        if item['exists']:
            try:
                digest = hashlib.sha256()
                with path.open('rb') as source:
                    header = source.read(2)
                    digest.update(header)
                    item['pe_header'] = header == b'MZ'
                    for chunk in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(chunk)
                item.update(size_bytes=path.stat().st_size, sha256=digest.hexdigest())
            except OSError as exc:
                item['read_error'] = str(exc)
        outputs.append(item)
    return outputs


def write_block_report(folder, error):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    outputs = inventory(folder)
    compiled = all(item['exists'] and item['pe_header'] for item in outputs)
    report = {'ok': False, 'build_status': 'compiled' if compiled else 'partial_or_not_built',
              'validation_status': 'blocked_by_windows_policy', 'runtime_verified': False,
              'winerror': error.winerror, 'blocked_file': error.blocked_file,
              'command': list(error.command), 'message': str(error), 'outputs': outputs,
              'next_step': 'Review the CodeIntegrity/Operational event log and obtain the applicable administrator approval or trusted publisher signing. Then use py -3 build.py --verify-existing; recompilation is not required merely to retry validation.'}
    path = folder / 'windows-policy-block.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # An earlier successful report must not make a currently blocked run look
    # verified. Keep both the block details and the explicit validation status.
    (folder / 'standalone-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def collect_diagnostics(folder):
    """Read existing outputs and recent Code Integrity events; no policy writes."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / 'windows-policy-block.json'
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {'ok':False,'validation_status':'not_run'}
    report['outputs'] = inventory(folder)
    report['diagnostic_note'] = 'This collection reads file hashes and Code Integrity events. Execution has not been approved by this tool.'
    tool = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'wevtutil.exe'
    events_path = folder / 'windows-codeintegrity-events.txt'
    if os.name == 'nt' and tool.is_file():
        try:
            result = subprocess.run([str(tool), 'qe', 'Microsoft-Windows-CodeIntegrity/Operational', '/c:20', '/rd:true', '/f:text'], capture_output=True, timeout=20, check=False)
            raw = result.stdout or result.stderr
            encoding = 'utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-16-le' if b'\0' in raw[:64] else 'utf-8'
            events_path.write_text(raw.decode(encoding, 'replace'), encoding='utf-8')
            report['event_log_exit_code'] = result.returncode
            report['event_log_file'] = str(events_path)
        except (OSError, subprocess.SubprocessError) as exc:
            report['event_log_error'] = str(exc)
    else:
        report['event_log_error'] = 'Code Integrity event collection requires Windows wevtutil.exe.'
    destination = folder / 'windows-policy-diagnostics.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return destination
