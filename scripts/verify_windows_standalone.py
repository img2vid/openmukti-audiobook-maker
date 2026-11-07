"""Verify each EXE from an empty directory with developer tools off PATH."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
if __package__:
    from .windows_policy import WindowsPolicyBlocked, is_policy_block
else:
    from windows_policy import WindowsPolicyBlocked, is_policy_block

PROGRAMS=('OpenmuktiAudiobookMaker','OpenmuktiAudiobookMakerCMD')


def clean_environment():
    environment=os.environ.copy()
    for key in list(environment):
        upper=key.upper()
        if upper.startswith(('PYTHON','OPENMUKTI_','OPENVOICE_','_PYI_','TESSDATA','CONDA','MAMBA','VIRTUAL_ENV','UV_')):
            environment.pop(key,None)
    system=Path(environment.get('SystemRoot',r'C:\Windows'))
    environment['PATH']=str(system/'System32')+os.pathsep+str(system)
    environment['PYINSTALLER_RESET_ENVIRONMENT']='1'
    return environment


def verify(folder):
    folder=Path(folder).resolve()
    results={}
    with tempfile.TemporaryDirectory(prefix='openmukti-standalone-') as temporary:
        root=Path(temporary)
        for name in PROGRAMS:
            location=root/name
            location.mkdir()
            executable=location/(name+'.exe')
            shutil.copy2(folder/executable.name,executable)
            report=location/'runtime-report.json'
            command=[str(executable),'--portable-check',str(report)]
            try:
                run=subprocess.run(command, cwd=location,env=clean_environment(),capture_output=True,text=True,
                    encoding='utf-8',errors='replace',timeout=900,check=False)
            except OSError as exc:
                if is_policy_block(exc):
                    raise WindowsPolicyBlocked(command, exc) from exc
                raise
            if not report.is_file():
                raise RuntimeError(f'{name} did not produce its standalone report. '+(run.stderr or run.stdout)[-1500:])
            result=json.loads(report.read_text(encoding='utf-8'))
            if run.returncode or not result.get('ok'):
                raise RuntimeError(f'{name} failed standalone verification: '+json.dumps(result,ensure_ascii=False))
            results[name]=result
    return {'ok':True,'method':'Each EXE copied alone; system-only PATH; no developer environment','programs':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,default=Path('dist'))
    args=parser.parse_args()
    report=verify(args.folder)
    destination=args.folder/'standalone-validation.json'
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(destination)
