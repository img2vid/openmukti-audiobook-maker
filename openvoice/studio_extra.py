"""Additional production commands for software maintenance and device configuration."""
from __future__ import annotations
import json
from pathlib import Path


def register_extra(group):
    def command(name,helptext,*fields):
        p=group.add_parser(name,help=helptext)
        for field in fields:
            p.add_argument(field)
        return p
    command('sound-credits','List source, credit and licensing information for all sound tracks','session')
    command('music-markers','Find low-energy times suitable for cuts','source')
    p=command('translation-pack','Extract an editable UI catalog or translate it with installed offline Argos models','source','locale','output')
    p.add_argument('--translate',action='store_true')
    command('emphasis','Suggest manuscript words for reviewed emphasis','source')
    command('language-spans','Report source offsets and language for mixed-script narration','source')
    command('recover','Recover missing archived assets by SHA-256','source','folder','output')
    command('migrate','Validate and upgrade an earlier portable project','source','output')
    p=command('models','Inventory, lock, transfer or convert approved local voice files','action','source')
    p.add_argument('destination',nargs='?')
    p.add_argument('--weight-files-only',action='store_true')
    p=command('voice-index','Manage cross-engine favorites, tags, accents, rights and collections','action')
    p.add_argument('--id',default='')
    p.add_argument('--value',default='')
    p.add_argument('--tag',default='')
    p.add_argument('--accent',default='')
    p.add_argument('--favorites',action='store_true')
    p=command('cast','Find, merge or split character profiles','action','project','name')
    p.add_argument('--target')
    p.add_argument('--passage',action='append',type=int,default=[])
    p.add_argument('--output')
    p=command('passages','Create or regenerate individually numbered audio passages','source','folder')
    p.add_argument('--only',action='append',type=int,default=[])
    p.add_argument('--engine',default='auto')
    p.add_argument('--voice',default='')
    p.add_argument('--model',default='')
    p=command('crossfade','Crossfade two recordings to a new file','first','second','output')
    p.add_argument('--seconds',type=float,default=1)
    command('compare-mixes','Compare two recordings by duration, loudness, peaks, clicks and clipping','reference','candidate')
    command('metadata','Export book and chapter metadata to Dublin Core XML or JSON','source','output')
    p=command('pipeline','Run or preview an ordered JSON production workflow','source')
    p.add_argument('--dry-run',action='store_true')
    command('layout-check','Check storyboard text collisions and safe zones','source')
    p=command('illustrate','Generate artwork using a selected local image-generation service','prompt','output')
    p.add_argument('--port',type=int,default=7860)
    p.add_argument('--width',type=int,default=768)
    p.add_argument('--height',type=int,default=768)
    p=command('versions','Manage and roll back single-file portable application installations','folder','action')
    p.add_argument('file',nargs='?',default='')
    p=command('gpu-runtime','Plan or install selected local GPU wheels into an engine environment','engine','folder')
    p.add_argument('wheels',nargs='+')
    p.add_argument('--install',action='store_true')
    p=command('test','Run a selected installed production self-check or the source test suite')
    p.add_argument('suite',choices=['portable','render','accessibility','source','languages'])
    p=command('scene-status','Track editing, synthesis and review status per scene','file')
    p.add_argument('--scene')
    p.add_argument('--set',choices=['draft','edited','synthesized','review','approved'])
    command('voice-repair','Check an installed Piper model and redownload verified assets if needed','voice')


def run_extra(a):
    from .studio_cli import report
    t=a.tool
    if t=='translation-pack':
        from .interface_language import compile_pack
        report(compile_pack(a.source,a.locale,a.output,a.translate))
    elif t in ('sound-credits','music-markers'):
        from .sound_studio import credits,transition_markers
        report(credits(a.session) if t=='sound-credits' else transition_markers(a.source))
    elif t in ('emphasis','language-spans'):
        from .documents import read_document
        from .editorial_studio import emphasis_advice
        from .localization_tools import language_spans
        report((emphasis_advice if t=='emphasis' else language_spans)(read_document(a.source)))
    elif t in ('recover','migrate'):
        from .project_tools import recover,migrate
        report(recover(a.source,a.folder,a.output) if t=='recover' else migrate(a.source,a.output))
    elif t=='models':
        from .voice_assets import inventory,check_lock,pack,unpack,convert_model,duplicate_files
        if a.action=='repair':
            from .voice_assets import repair_from_lock
            if not a.destination:
                raise ValueError('Supply a lock file and backup folder')
            report(repair_from_lock(a.source,a.destination))
        elif a.action=='duplicates':
            report(duplicate_files(a.source))
        elif a.action=='verify':
            spec=json.loads(Path(a.source).read_text(encoding='utf-8'))
            rows=check_lock((Path(a.source).resolve().parent/spec['root']).resolve(),spec['files'])
            report(rows)
            return int(bool(rows))
        elif a.action in ('lock','list'):
            from .security_tools import staged_file
            from .voice_library import _atomic_json
            rows=inventory(a.source,a.weight_files_only)
            if a.action=='list':
                report(rows)
            else:
                if not a.destination:
                    raise ValueError('Specify a lock file outside the model folder')
                target=Path(a.destination).resolve()
                root=Path(a.source).resolve(strict=True)
                if target.is_relative_to(root):
                    raise ValueError('Store the lock outside the model folder')
                import os
                try:
                    base=os.path.relpath(root,target.parent)
                except ValueError:
                    base=str(root)
                _atomic_json(target,{'root':base,'files':rows})
        else:
            ops={'pack':pack,'unpack':unpack,'convert':convert_model}
            if a.action not in ops or not a.destination:
                raise ValueError('Use list, lock, verify, duplicates, pack, unpack or convert')
            report(ops[a.action](a.source,a.destination))
    elif t=='voice-index':
        from .voice_assets import registry
        if a.action not in ('list','set','collections','collection'):
            raise ValueError('Unknown index action')
        report(registry(a.action,a.id,a.value,tag=a.tag,accent=a.accent,favorites=a.favorites))
    elif t=='voice-repair':
        from .voice_catalog import catalog_voice,installed_catalog_voice,download_voice
        v=catalog_voice(a.voice,allow_network=True)
        if not v:
            raise ValueError('Unknown catalog voice')
        report(installed_catalog_voice(v) or download_voice(v))
    elif t=='cast':
        from .character_voices import VoiceProject
        from .character_tools import update,search
        from .security_tools import staged_file
        project=VoiceProject.load(a.project)
        if a.action=='search':
            report(search(project,a.name))
        else:
            if a.action not in ('merge','split') or not a.target or not a.output:
                raise ValueError('Supply merge/split, target name and output project')
            if a.action=='split' and not a.passage:
                raise ValueError('Choose passages with --passage N')
            update(project,a.name,a.target,passages=a.passage or None,remove=a.action=='merge')
            with staged_file(a.output) as stage:
                project.save(stage)
    elif t=='passages':
        from .production_extras import passages
        report(passages(a.source,a.folder,indices=a.only,engine=a.engine,voice=a.voice,model=a.model))
    elif t=='compare-mixes':
        from .production_extras import compare_mixes
        report(compare_mixes(a.reference,a.candidate))
    elif t=='crossfade':
        from .production_extras import transition
        report(transition(a.first,a.second,a.output,a.seconds))
    elif t=='metadata':
        from .production_extras import distribution_metadata
        report(distribution_metadata(a.source,a.output))
    elif t=='pipeline':
        from .production_extras import pipeline
        report(pipeline(a.source,dry=a.dry_run))
    elif t=='illustrate':
        from .integrations import illustration
        report(illustration(a.prompt,a.output,a.port,a.width,a.height))
    elif t=='layout-check':
        from .subtitle_tools import layout_check
        findings=layout_check(json.loads(Path(a.source).read_text(encoding='utf-8')))
        report(findings)
        return int(bool(findings))
    elif t=='versions':
        from .platform_tools import deployment
        if a.action not in ('install','rollback','list','launch'):
            raise ValueError('Unknown version action')
        report(deployment(a.folder,a.action,a.file))
    elif t=='gpu-runtime':
        from .platform_tools import gpu_wheels
        report(gpu_wheels(a.engine,a.folder,a.wheels,a.install))
    elif t=='test':
        from .studio_selftest import selftest
        rows=selftest(a.suite)
        report(rows)
        return int(not rows['ok'])
    elif t=='scene-status':
        from .voice_library import _atomic_json
        path=Path(a.file)
        data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if a.set:
            if not a.scene:
                raise ValueError('Name the scene with --scene')
            data[a.scene]=a.set
            _atomic_json(path,data)
        report(data)
    else:
        raise ValueError('Unknown production command')
    return 0
