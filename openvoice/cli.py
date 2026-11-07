from __future__ import annotations
import argparse
import sqlite3
import zipfile
import subprocess
import json
import sys
import tempfile
from pathlib import Path
from . import __version__
from .audio import write_raw_pcm
from .audiofx import audio_info, process_audio
from .documents import read_document
from .fftools import media_tools_status
from .engines import SpeechSettings, all_engines, get_engine
from .service import JobOptions, render_text, speak_text
from .texttools import TOOLS, text_stats, transform
from .video import ASPECTS, HEIGHTS, VideoOptions, render_video
from .audiobooks import load_manifest, discover_books, export_books, BookExportOptions
from .edition import APP_NAME, EDITION, GUTENBERG_ENABLED
from .voice_catalog import fetch_catalog, download_selected, voice_download_size
from .character_voices import VoiceProject, auto_profiles, detect_language, detected_languages, read_name_list, merge_auto_profiles
from .multivoice import render_multivoice,render_multivoice_video
from .piper_models import discover_voices, speaker_list
from .project_archive import ProjectData, save_project, load_project
from .progress import ConsoleProgress, emit, subprogress
from . import narration_text as _narration_text  # registers speech text tools
if GUTENBERG_ENABLED:
    from .gutenberg import clean_gutenberg, GutenbergOptions

def _general(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--engine', choices=['auto', *all_engines().keys()], default='auto')
    parser.add_argument('--cache-dir', default='', help='Reuse verified narration chunks across jobs and after interruption')
    parser.add_argument('--refresh-cache', action='store_true', help='Regenerate chunks in the selected cache')
    parser.add_argument('--performance-profile', choices=['low','balanced','fast'], default='', help='Opt-in CPU thread limit for TTS processing')
    parser.add_argument('--gpu', action=argparse.BooleanOptionalAction, default=None, help='Try GPU in compatible speech engines; fall back to CPU')
    parser.add_argument('-n', '--voice', default='')
    parser.add_argument('-s', '--rate', type=int, default=0)
    parser.add_argument('-p', '--pitch', type=int, default=0)
    parser.add_argument('-v', '--volume', type=int, default=100)
    parser.add_argument('--model', default='')
    parser.add_argument('--speaker-id', type=int, default=None, help='Piper speaker ID (0-based index for multi-speaker models)')
    parser.add_argument('-d', '--dictionary', action='append', default=[])
    parser.add_argument('--ipa-dictionary',action='append',default=[],help='IPA pronunciation dictionary (.json or .tsv); supports per-language words')
    parser.add_argument('--language',default='auto',help='Language for IPA rule matching (ISO code; auto detects script/text)')
    parser.add_argument('--repair-ocr', action='store_true')
    parser.add_argument('--chunk-size', type=int, default=450)
    parser.add_argument('--pause-ms', type=int, default=80)
    parser.add_argument('--apply', action='append', default=[], choices=list(TOOLS), metavar='TOOL')

def _text_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('text', nargs='?')
    parser.add_argument('-t', '--text', dest='text_args', action='append')
    parser.add_argument('-f', '--file', action='append')
    parser.add_argument('-i', '--stdin', action='store_true')

def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='openmukti', description=f'{APP_NAME} Version 1. Inline IPA: <ipa:həˈloʊ|hello> (no dictionary required)')
    parser.add_argument('--version', action='version', version=f'{APP_NAME} {__version__}')
    parser.add_argument('-?', action='help')
    sub = parser.add_subparsers(dest='command', required=True)
    from .studio_cli import register as register_studio
    register_studio(sub)
    publish = sub.add_parser('publish-book', help='Create a chaptered M4B or RSS feed from a chapter manifest')
    publish.add_argument('manifest')
    publish.add_argument('output')
    overlay = sub.add_parser('read-along', help='Export an MP3 and timed text as a synchronized EPUB')
    for argument in ('audio', 'timing', 'output'):
        overlay.add_argument(argument)
    overlay.add_argument('--title', required=True)
    overlay.add_argument('--language', required=True)
    subtitles = sub.add_parser('subtitle-pack', help='Bundle multilingual subtitles with a SHA-256 manifest')
    subtitles.add_argument('output')
    subtitles.add_argument('tracks', nargs='+', metavar='LANG=FILE')
    compare = sub.add_parser('audio-regression', help='Compare an aligned PCM WAV render against an approved reference')
    compare.add_argument('reference')
    compare.add_argument('candidate')
    compare.add_argument('--max-rms-error', type=float, default=0.0)
    captions = sub.add_parser('captions', help='Export timed JSON, VTT or SRT cues as SRT, WebVTT or ASS')
    captions.add_argument('source')
    captions.add_argument('output')
    captions.add_argument('--font', default='Arial', help='ASS subtitle font')
    captions.add_argument('--font-size', type=int, default=48, help='ASS subtitle size')
    captions.add_argument('--alignment', type=int, default=2, help='ASS numpad alignment 1..9')
    release = sub.add_parser('release-archive', help='Package a finished book folder with a SHA-256 manifest')
    release.add_argument('folder')
    release.add_argument('output')
    quality = sub.add_parser('audio-quality', help='Measure loudness, true peak and prolonged silences')
    quality.add_argument('file')
    sub.add_parser('environment-sbom', help='List packages, versions and declared licenses in the active Python environment')
    sub.add_parser('gui', help='Start desktop GUI')
    ocr = sub.add_parser('ocr', help='Recognize scanned PDFs, images, ZIP/CBZ books or page-image folders locally')
    ocr.add_argument('--gpu', action=argparse.BooleanOptionalAction, default=None)
    ocr.add_argument('source', nargs='?')
    ocr.add_argument('-w', '--output', help='Write recognized UTF-8 text')
    ocr.add_argument('--json', action='store_true', help='Output page text, confidence and warnings as JSON')
    ocr.add_argument('--status', action='store_true', help='List Tesseract availability and installed languages')
    ocr.add_argument('--language', default='eng')
    ocr.add_argument('--dpi', type=int, default=300)
    ocr.add_argument('--enhance-blur',action='store_true')
    ocr.add_argument('--historic-print',action='store_true')
    ocr.add_argument('--preprocessing', choices=['auto','adaptive','otsu','contrast','original'], default='auto')
    ocr.add_argument('--contrast', type=float, default=1.4)
    ocr.add_argument('--psm', type=int, choices=[3,4,6,11,12], default=3)
    area = ocr.add_mutually_exclusive_group()
    area.add_argument('--region', type=int, nargs=4, metavar=('LEFT', 'TOP', 'RIGHT', 'BOTTOM'),
                      help='Recognize this rectangle in oriented page pixels')
    area.add_argument('--corners', type=int, nargs=8, metavar='N',
                      help='Rectify a photographed page: x y for TL, TR, BR, BL')
    ocr.add_argument('--first-page', type=int, default=1)
    ocr.add_argument('--last-page', type=int, default=0)
    ocr.add_argument('--force-ocr', action='store_true')
    ocr.add_argument('--split-spreads', action='store_true')
    ocr.add_argument('--no-deskew', action='store_true')
    ocr.add_argument('--no-denoise', action='store_true')
    ocr.add_argument('--no-rotate', action='store_true')
    ocr.add_argument('--correct', action='store_true', help='Apply top English spelling/OCR suggestions to recognized text')
    ocr.add_argument('--searchable-pdf', default='', help='Export rasterized searchable PDF with invisible OCR text layer')
    spelling = sub.add_parser('spellcheck', help='Offline English spelling and OCR restoration')
    spelling.add_argument('-f', '--file', required=True)
    spelling.add_argument('-w', '--output')
    spelling.add_argument('--correct', action='store_true')
    spelling.add_argument('--safe-only', action='store_true')
    spelling.add_argument('--check-names', action='store_true')
    spelling.add_argument('--json', action='store_true')
    pack = sub.add_parser('project-pack', help='Create a portable .oamproj from text, voices and images')
    pack.add_argument('-f','--file',required=True)
    pack.add_argument('-w','--output',required=True)
    pack.add_argument('--voice-project',help='Optional Character Voices JSON file')
    pack.add_argument('--images',nargs='*',default=[])
    pack.add_argument('--model',default='',help='Optional installed Piper ONNX model')
    pack.add_argument('--ipa-dictionary',default='',help='Optional IPA dictionary')
    unpack = sub.add_parser('project-unpack',help='Verify and unpack a complete Openmukti project')
    unpack.add_argument('project')
    unpack.add_argument('--output-dir',required=True)
    create = sub.add_parser('project-render',help='Render from a saved project with all its character voices')
    create.add_argument('project')
    create.add_argument('-w','--output',required=True)
    verify = sub.add_parser('project-verify',help='Verify all checksums and content in a saved project')
    verify.add_argument('project')
    catalog = sub.add_parser('voice-catalog',help='Browse Piper voices from the official language-organized catalog')
    catalog.add_argument('--language',default='',help='Language code or English language name')
    catalog.add_argument('--refresh',action='store_true')
    catalog.add_argument('--json',action='store_true')
    downloads = sub.add_parser('voice-download',help='Download selected Piper ONNX model(s), verified by checksum')
    downloads.add_argument('models',nargs='*',help='Exact catalog voice keys, e.g. en_US-amy-medium')
    downloads.add_argument('--language',default='',help='Download all voices for a language, requires --all')
    downloads.add_argument('--all',action='store_true',help='Download all catalog models or all in --language')
    downloads.add_argument('--yes',action='store_true',help='Confirm potentially large downloads without interactive prompt')
    downloads.add_argument('--refresh',action='store_true')
    detect = sub.add_parser('detect-language',help='Detect language from one or more paragraphs, offline heuristic')
    _text_args(detect)
    detect.add_argument('--json',action='store_true')
    create_profiles = sub.add_parser('character-profiles',help='Detect characters and create a multilingual voice project')
    _text_args(create_profiles)
    create_profiles.add_argument('-w','--output',required=True)
    create_profiles.add_argument('--names',action='append',default=[],help='Additional UTF-8 text, CSV, JSON or GZip name list; repeatable')
    create_profiles.add_argument('--update-project',help='Refresh automatic fields in an existing voice JSON; keep manual edits')
    create_profiles.add_argument('--report',help='Optional JSON attribution/evidence report, with source quote offsets')
    multi = sub.add_parser('multivoice',help='Create character-voiced audio or video from a voice project')
    _text_args(multi)
    multi.add_argument('--project',required=True,help='Saved character voice profile JSON')
    multi.add_argument('--gpu',action=argparse.BooleanOptionalAction,default=None)
    multi.add_argument('--cache-dir',default='')
    multi.add_argument('--images',nargs='*',default=[],help='Optional cover images for animated video; required for classic slideshow')
    multi.add_argument('-w','--output',required=True)
    multi.add_argument('--ipa-dictionary',action='append',default=[],help='IPA dictionary for character voice synthesis')
    multi.add_argument('--auto-tag',action='store_true',help='Guess character from dialogue attribution; review output')
    multi.add_argument('--aspect',default='16:9',help='Aspect ratio e.g. 16:9, 9:16, 19:10')
    multi.add_argument('--animation', choices=list(__import__('openvoice.animated_video',fromlist=['MODES']).MODES),default='none',help='Animated text / simulated handwriting modes')
    multi.add_argument('--dimensions',default='',help='Exact even-pixel dimensions e.g. 1920x1080')
    multi.add_argument('--font-file',default='',help='TTF/OTF font supporting the text scripts')
    multi.add_argument('--font-size',type=int,default=0,help='Text font size, 0 = automatic')
    multi.add_argument('--timing-file',default='',help='Timestamped transcript: JSON, SRT or WebVTT')
    multi.add_argument('--text-color',default='FFFFFF',help='Text RGB hex')
    multi.add_argument('--panel-opacity',type=int,default=165,help='Readable text panel opacity 0..255')
    multi.add_argument('--pen-width',type=int,default=0,help='Handwriting/calligraphy pen thickness, 0=auto')
    multi.add_argument('--nib-angle',type=int,default=-32,help='Calligraphy pen angle, -80..80 degrees')
    multi.add_argument('--stroke-library',default='',help='Unicode Stroke Studio trajectories JSON')
    multi.add_argument('--strict-strokes',action='store_true',help='Require real hand-drawn trajectories for every cluster')
    multi.add_argument('--paper-grain',type=int,default=14,help='Paper texture amount 0..80')
    multi.add_argument('--brush-dryness',type=int,default=12,help='Dry brush texture amount 0..80')
    multi.add_argument('--pen-tool',choices=['auto','pencil','ballpoint','fountain','brush','broad-nib'],default='auto',help='Physical drawing instrument')
    multi.add_argument('--resolution',choices=list(HEIGHTS),default='720p')
    ipa_check = sub.add_parser('ipa-check',help='Validate IPA pronunciation dictionary and show entries')
    ipa_check.add_argument('dictionary',nargs='+')
    ipa_check.add_argument('--language',default='*')
    media = sub.add_parser('media-tools', help='Show built-in FFmpeg and FFprobe availability')
    media.add_argument('--json', action='store_true')
    setup = sub.add_parser('engine-install', help='Download isolated CPU dependencies for Kokoro, Kitten, Pocket or Coqui')
    setup.add_argument('engine', choices=['kokoro','kitten','pocket','coqui','all'])
    engines = sub.add_parser('engines', help='List installed speech engines')
    engines.add_argument('--json', action='store_true')
    voices = sub.add_parser('voices', help='List available voices')
    voices.add_argument('--engine', choices=['auto', *all_engines().keys()], default='auto')
    voices.add_argument('--model', default='')
    voices.add_argument('--speakers', action='store_true', help='List every speaker ID and name in installed Piper models or --model')
    voices.add_argument('--json', action='store_true')
    speak = sub.add_parser('speak', help='Speak text')
    _general(speak)
    _text_args(speak)
    render = sub.add_parser('render', help='Render speech to audio')
    _general(render)
    _text_args(render)
    render.add_argument('-w', '--output', required=True)
    batch = sub.add_parser('batch', help='Convert multiple documents')
    _general(batch)
    batch.add_argument('files', nargs='+')
    batch.add_argument('--output-dir', required=True)
    batch.add_argument('--format', choices=['wav', 'mp3', 'flac', 'ogg', 'm4a', 'opus', 'aac', 'aiff', 'wma'], default='wav')
    batch.add_argument('--dry-run', action='store_true')
    batch.add_argument('--skip-existing', action='store_true')
    tools = sub.add_parser('tools', help='List all available text transformations')
    tools.add_argument('--json', action='store_true')
    tools.add_argument('--group', default='')
    change = sub.add_parser('transform', help='Apply text transformations')
    _text_args(change)
    change.add_argument('--apply', action='append', required=True, choices=list(TOOLS), metavar='TOOL')
    change.add_argument('-w', '--output')
    stats = sub.add_parser('stats', help='Report document and reading statistics')
    _text_args(stats)
    stats.add_argument('--wpm', type=int, default=160)
    stats.add_argument('--json', action='store_true')
    split = sub.add_parser('split', help='Split a text into chunks or sentences')
    _text_args(split)
    split.add_argument('--chunk-size', type=int, default=450)
    split.add_argument('--sentences', action='store_true')
    split.add_argument('--json', action='store_true')
    inspect = sub.add_parser('audio-info', help='Inspect an existing audio file')
    inspect.add_argument('input')
    audio = sub.add_parser('audio', help='Modify existing audio with FFmpeg')
    audio.add_argument('operation', choices=['convert', 'join', 'trim', 'speed', 'gain', 'normalize', 'reverse', 'fade-in', 'fade-out', 'mono', 'stereo', 'resample', 'denoise', 'compress', 'deess', 'equalize', 'pan', 'trim-silence'])
    audio.add_argument('inputs', nargs='+')
    audio.add_argument('-w', '--output', required=True)
    audio.add_argument('--start', type=float, default=0)
    audio.add_argument('--duration', type=float, default=0)
    audio.add_argument('--speed', type=float, default=1)
    audio.add_argument('--gain', type=float, default=0)
    audio.add_argument('--sample-rate', type=int, default=0)
    audio.add_argument('--channels', type=int, default=0)
    audio.add_argument('--fade-seconds', type=float, default=1)
    audio.add_argument('--compression', type=int, default=50)
    audio.add_argument('--eq-frequency', type=float, default=1000, help='Center frequency for equalize (Hz)')
    audio.add_argument('--eq-gain', type=float, default=0, help='Equalizer gain (-24..24 dB)')
    audio.add_argument('--pan', type=float, default=0, help='Stereo pan position (-1..+1)')
    audio.add_argument('--silence-db', type=float, default=-45, help='Silence trim threshold (dB)')
    audio.add_argument('--silence-duration', type=float, default=0.3, help='Minimum silence duration (seconds)')
    video = sub.add_parser('video', help='Create an audiobook video from images with narration')
    _general(video)
    _text_args(video)
    video.add_argument('--images', nargs='*', default=[], help='Optional cover images for animation, required for classic slideshow')
    video.add_argument('--audio', help='Optional existing audio; skips speech synthesis')
    video.add_argument('-w', '--output', required=True, help='MP4, MKV, MOV or WebM video')
    video.add_argument('--aspect', default='16:9',help='Preset or custom ratio W:H')
    video.add_argument('--caption-preset',choices=['custom','white on black','yellow on black','black on white'],default='custom')
    video.add_argument('--safe-margin',type=float,default=.09)
    video.add_argument('--storyboard', default='', help='Layered cover, scene and overlay JSON design')
    video.add_argument('--animation', choices=list(__import__('openvoice.animated_video',fromlist=['MODES']).MODES),default='none',help='Animated text / simulated handwriting modes')
    video.add_argument('--dimensions',default='',help='Exact even-pixel dimensions e.g. 1920x1080')
    video.add_argument('--font-file',default='',help='TTF/OTF font supporting the text scripts')
    video.add_argument('--font-size',type=int,default=0,help='Text font size, 0 = automatic')
    video.add_argument('--timing-file',default='',help='Timestamped transcript: JSON, SRT or WebVTT')
    video.add_argument('--text-color',default='FFFFFF',help='Text RGB hex')
    video.add_argument('--panel-opacity',type=int,default=165,help='Readable text panel opacity 0..255')
    video.add_argument('--pen-width',type=int,default=0,help='Handwriting/calligraphy pen thickness, 0=auto')
    video.add_argument('--nib-angle',type=int,default=-32,help='Calligraphy pen angle, -80..80 degrees')
    video.add_argument('--stroke-library',default='',help='Unicode Stroke Studio trajectories JSON')
    video.add_argument('--strict-strokes',action='store_true',help='Require real hand-drawn trajectories for every cluster')
    video.add_argument('--paper-grain',type=int,default=14,help='Paper texture amount 0..80')
    video.add_argument('--brush-dryness',type=int,default=12,help='Dry brush texture amount 0..80')
    video.add_argument('--pen-tool',choices=['auto','pencil','ballpoint','fountain','brush','broad-nib'],default='auto',help='Physical drawing instrument')
    video.add_argument('--resolution', choices=list(HEIGHTS), default='720p')
    video.add_argument('--fps', type=int, choices=[24, 25, 30, 60], default=30)
    video.add_argument('--fit', choices=['contain', 'cover'], default='contain')
    video.add_argument('--background', default='black')
    video.add_argument('--captions', action='store_true', help='Write an approximate-timing SRT subtitle sidecar')
    video.add_argument('--crf', type=int, default=23)
    if GUTENBERG_ENABLED:
        gt = sub.add_parser('gutenberg', help='Clean Gutenberg text or bulk ebook files')
        gt.add_argument('files', nargs='+')
        gt.add_argument('--output-dir', required=True)
        gt.add_argument('--keep-toc', action='store_true')
        gt.add_argument('--keep-placeholders', action='store_true')
        gt.add_argument('--keep-page-numbers', action='store_true')
        gt.add_argument('--no-reflow', action='store_true')
        gt.add_argument('--split-chapters', action='store_true')
        gt.add_argument('--json', action='store_true')
    books = sub.add_parser('audiobooks', help='Bulk audio-only or video audiobook production with optional multi-speaker narration')
    _general(books)
    source = books.add_mutually_exclusive_group(required=True)
    source.add_argument('--folder', help='Folder with one subfolder per book; auto-match covers by filename/chapter number')
    source.add_argument('--manifest', help='JSON manifest with explicit books, chapters and cover paths')
    books.add_argument('--output-dir', required=True)
    books.add_argument('--mode', choices=['book','chapters','both'], default='both')
    books.add_argument('--format', choices=['mp4','mkv','mov','webm'], default='mp4')
    books.add_argument('--output-type',choices=['audio','video'],default='video')
    books.add_argument('--audio-format',choices=['wav','mp3','m4a','flac','ogg'],default='mp3')
    books.add_argument('--voices-project',help='Voice project JSON shared by all books; individual manifests can override')
    if GUTENBERG_ENABLED:
        books.add_argument('--gutenberg', action='store_true', help='Clean Gutenberg headers, footers and artifacts before narration')
    books.add_argument('--dry-run', action='store_true')
    books.add_argument('--skip-existing', action='store_true')
    books.add_argument('--fail-fast', action='store_true')
    books.add_argument('--aspect', default='16:9',help='Preset or custom ratio W:H')
    books.add_argument('--animation', choices=list(__import__('openvoice.animated_video',fromlist=['MODES']).MODES),default='none',help='Animated text / simulated handwriting modes')
    books.add_argument('--dimensions',default='',help='Exact even-pixel dimensions e.g. 1920x1080')
    books.add_argument('--font-file',default='',help='TTF/OTF font supporting the text scripts')
    books.add_argument('--font-size',type=int,default=0,help='Text font size, 0 = automatic')
    books.add_argument('--timing-file',default='',help='Timestamped transcript: JSON, SRT or WebVTT')
    books.add_argument('--text-color',default='FFFFFF',help='Text RGB hex')
    books.add_argument('--panel-opacity',type=int,default=165,help='Readable text panel opacity 0..255')
    books.add_argument('--pen-width',type=int,default=0,help='Handwriting/calligraphy pen thickness, 0=auto')
    books.add_argument('--nib-angle',type=int,default=-32,help='Calligraphy pen angle, -80..80 degrees')
    books.add_argument('--stroke-library',default='',help='Unicode Stroke Studio trajectories JSON')
    books.add_argument('--strict-strokes',action='store_true',help='Require real hand-drawn trajectories for every cluster')
    books.add_argument('--paper-grain',type=int,default=14,help='Paper texture amount 0..80')
    books.add_argument('--brush-dryness',type=int,default=12,help='Dry brush texture amount 0..80')
    books.add_argument('--pen-tool',choices=['auto','pencil','ballpoint','fountain','brush','broad-nib'],default='auto',help='Physical drawing instrument')
    books.add_argument('--resolution', choices=list(HEIGHTS), default='720p')
    books.add_argument('--fps', type=int, choices=[24,25,30,60], default=30)
    books.add_argument('--fit', choices=['contain','cover'], default='contain')
    books.add_argument('--captions', action='store_true')
    books.add_argument('--crf', type=int, default=23)
    books.add_argument('--json', action='store_true')
    library = sub.add_parser('library', help='Project library: organize, search, analyze and archive projects')
    library.add_argument('action', choices=['add', 'remove', 'list', 'search', 'category', 'tags', 'favorite',
                                            'note', 'bookmark', 'rename', 'duplicates', 'storage', 'health'])
    library.add_argument('paths', nargs='*', help='Project files or names, depending on the action')
    library.add_argument('--index', default='openmukti-library.json', help='Library index JSON file')
    library.add_argument('--category', default='')
    library.add_argument('--tags', default='', help='Comma-separated tags')
    library.add_argument('--note', default='')
    library.add_argument('--query', default='')
    library.add_argument('--favorites', action='store_true', help='Limit search/list to favorites')
    library.add_argument('--text-search', action='store_true', help='Also search .oamproj manuscript text')
    library.add_argument('--pattern', default='', help='Rename match text or regular expression')
    library.add_argument('--replacement', default='', help='Rename replacement (supports \\1 with --regex)')
    library.add_argument('--regex', action='store_true')
    library.add_argument('--dry-run', action='store_true')
    library.add_argument('--json', action='store_true')
    chapters_cmd = sub.add_parser('chapters', help='Detect chapters, build a table of contents and track completion')
    chapters_cmd.add_argument('action', choices=['detect', 'toc', 'scenes', 'headers', 'estimate',
                                                 'set-status', 'status-summary'])
    chapters_cmd.add_argument('-f', '--file')
    chapters_cmd.add_argument('--status-file', default='', help='Chapter status JSON (status actions)')
    chapters_cmd.add_argument('--chapter', default='', help='Chapter title for set-status')
    chapters_cmd.add_argument('--status', default='', choices=['', 'drafted', 'reviewed', 'completed'])
    chapters_cmd.add_argument('--rule', action='append', default=[], help='Custom full-line chapter regex; repeatable')
    chapters_cmd.add_argument('--style', choices=['markdown', 'plain', 'json'], default='markdown')
    chapters_cmd.add_argument('--wpm', type=int, default=160)
    chapters_cmd.add_argument('--json', action='store_true')
    proof = sub.add_parser('proofread', help='Editorial reports: names, dialogue punctuation, readability, terminology')
    proof.add_argument('action', choices=['names', 'dialogue', 'ocr-artifacts', 'readability',
                                          'terminology', 'pronunciation-audit'])
    proof.add_argument('-f', '--file', action='append', required=True,
                       help='Manuscript file; repeat for cross-chapter terminology')
    proof.add_argument('--dictionary', action='append', default=[], help='Word list for the pronunciation audit')
    proof.add_argument('--overrides', action='append', default=[], help='Pronunciation override dictionary files')
    proof.add_argument('-w', '--output', help='Write the JSON report to a file')
    name_files = sub.add_parser('name-files', help='Render export file names from a naming pattern')
    name_files.add_argument('pattern', help='Pattern with {title} {author} {chapter} {number:03} {language} {date}')
    name_files.add_argument('chapters', nargs='*', help='Chapter titles to name')
    name_files.add_argument('--title', default='')
    name_files.add_argument('--author', default='')
    name_files.add_argument('--language', default='en')
    name_files.add_argument('--narrator', default='')
    sample = sub.add_parser('sample', help='Create a promotional audiobook excerpt with fades')
    sample.add_argument('source')
    sample.add_argument('output')
    sample.add_argument('--start', type=float, default=0.0)
    sample.add_argument('--duration', type=float, default=60.0)
    sample.add_argument('--fade-seconds', type=float, default=2.0)
    notes_cmd = sub.add_parser('release-notes', help='Generate Markdown release notes from a changes JSON file')
    notes_cmd.add_argument('changes', help='JSON list of {"kind": "added|fixed|changed|removed", "text": ...}')
    notes_cmd.add_argument('--version', required=True)
    notes_cmd.add_argument('--title', default='')
    notes_cmd.add_argument('-w', '--output')
    attribution = sub.add_parser('attribution', help='Compile a credits and licensing document from an assets JSON file')
    attribution.add_argument('assets', help='JSON list of {"name", "type", "source", "license", "attribution"}')
    attribution.add_argument('--project', required=True, help='Book title')
    attribution.add_argument('--author', default='')
    attribution.add_argument('--narrator', default='')
    attribution.add_argument('-w', '--output')
    transcript = sub.add_parser('transcript', help='Export a formatted transcript (.pdf, .html or .txt)')
    transcript.add_argument('-f', '--file', required=True)
    transcript.add_argument('-w', '--output', required=True)
    transcript.add_argument('--title', default='')
    transcript.add_argument('--author', default='')
    transcript.add_argument('--rule', action='append', default=[], help='Custom chapter detection regex')
    production = sub.add_parser('production', help='Workflow stages, QC checkpoints, approvals, estimates and logs')
    production.add_argument('action', choices=['stage', 'checkpoint', 'approve', 'dashboard',
                                               'estimate', 'forecast', 'log', 'log-summary'])
    production.add_argument('--board', default='openmukti-production.json', help='Production board JSON')
    production.add_argument('--chapter', default='')
    production.add_argument('--stage', default='', choices=['', 'imported', 'corrected', 'narrated', 'mastered', 'exported'])
    production.add_argument('--checkpoint', default='')
    production.add_argument('--passed', action='store_true')
    production.add_argument('-f', '--file', help='Manuscript for estimate/forecast')
    production.add_argument('--wpm', type=int, default=160)
    production.add_argument('--rtf', type=float, default=0.5, help='Measured synthesis realtime factor')
    production.add_argument('--format', default='wav', help='Forecast audio format')
    production.add_argument('--log-file', default='', help='Production JSONL log (log actions)')
    production.add_argument('--event', default='')
    production.add_argument('--level', default='info', choices=['debug', 'info', 'warning', 'error'])
    production.add_argument('--detail', action='append', default=[], help='Log field key=value; repeatable')
    production.add_argument('--redact', action='append', default=[], help='Field names to redact in the log')
    production.add_argument('--json', action='store_true')
    hardware = sub.add_parser('hardware-check', help='Report CPU, disk space, ONNX providers and acceleration compatibility')
    hardware.add_argument('--folder', default='.', help='Folder to check free storage space')
    hardware.add_argument('--profile', choices=['low','balanced','fast'], help='Apply CPU profile before checking')
    hardware.add_argument('--gpu', action=argparse.BooleanOptionalAction, default=None, help='Request GPU when available for compatible engines')
    tag = sub.add_parser('tag-audio', help='Add audio metadata or embedded cover without reencoding the original audio')
    tag.add_argument('input')
    tag.add_argument('-w', '--output', required=True)
    tag.add_argument('--tag', action='append', default=[], help='Metadata KEY=VALUE; repeatable')
    tag.add_argument('--cover', default='', help='JPG or PNG to embed in MP3/FLAC/M4A/M4B')
    voice_lib = sub.add_parser('voice-library', help='Offline voice favorites, tags, collections, duplicate checking and portable voice packs')
    voice_lib.add_argument('action', choices=['list','favorite','unfavorite','tags','collection','collections','duplicates','export-pack','import-pack'])
    voice_lib.add_argument('names', nargs='*', help='Voice name(s), collection name and voice names, or pack path')
    voice_lib.add_argument('--metadata-file', default='', help='Optional metadata JSON path')
    voice_lib.add_argument('--tags', default='', help='Comma-separated voice labels')
    voice_lib.add_argument('--favorites', action='store_true')
    voice_lib.add_argument('--tag', default='', help='Filter by tag')
    voice_lib.add_argument('-w', '--output', help='Destination for exported voice pack')
    voice_lib.add_argument('--target', help='Directory for imported Piper voices')
    voice_lib.add_argument('--overwrite', action='store_true', help='Allow overwriting existing voice files')
    voice_lib.add_argument('--json', action='store_true')
    scripts = sub.add_parser('script-check', help='Offline mixed-language/script and Unicode validation report')
    scripts.add_argument('-f', '--file', required=True)
    scripts.add_argument('-w', '--output')
    scripts.add_argument('--max-issues', type=int, default=100)
    compliance = sub.add_parser('publication-check', help='Audit export files and basic publishing metadata')
    compliance.add_argument('folder')
    compliance.add_argument('--title', default='')
    compliance.add_argument('--author', default='')
    compliance.add_argument('--language', default='')
    compliance.add_argument('--cover', default='')
    compliance.add_argument('-w', '--output')
    segments = sub.add_parser('segment-audit', help='Check output files against a rendered-segment manifest')
    segments.add_argument('manifest')
    segments.add_argument('folder')
    segments.add_argument('-w', '--output')
    return parser

def make_legacy_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='openmukti', description=f'{APP_NAME} — direct command-line mode')
    _general(p)
    _text_args(p)
    p.add_argument('-w', '--output')
    p.add_argument('-o', '--raw-stdout', action='store_true')
    p.add_argument('--stdout-wav', action='store_true')
    p.add_argument('-l', '--list-voices', action='store_true')
    p.add_argument('-?', action='help')
    p.add_argument('--version', action='version', version=f'{APP_NAME} {__version__}')
    return p

def _validate(args: argparse.Namespace) -> None:
    if getattr(args, 'speaker_id', None) is not None and args.speaker_id < 0:
        raise ValueError('Piper speaker ID must be 0 or greater')
    if not -10 <= args.rate <= 10:
        raise ValueError('Rate must be between -10 and 10')
    if not -10 <= args.pitch <= 10:
        raise ValueError('Pitch must be between -10 and 10')
    if not 0 <= args.volume <= 100:
        raise ValueError('Volume must be between 0 and 100')
    if not 16 <= args.chunk_size <= 10000:
        raise ValueError('Chunk size must be 16..10000')

def _load_input(args: argparse.Namespace) -> str:
    parts = []
    if args.text:
        parts.append(args.text)
    parts.extend(args.text_args or [])
    for file in args.file or []:
        parts.append(read_document(file))
    if args.stdin or (not parts and (not sys.stdin.isatty())):
        parts.append(sys.stdin.read())
    result = '\n\n'.join(parts).strip()
    if not result:
        raise ValueError('No input text: pass text, -t, -f or --stdin')
    return result

def _settings(args: argparse.Namespace) -> SpeechSettings:
    _validate(args)
    return SpeechSettings(voice=args.voice, rate=args.rate, pitch=args.pitch, volume=args.volume, model=args.model, speaker_id=getattr(args, 'speaker_id', None), language=args.language)

def _options(args: argparse.Namespace) -> JobOptions:
    return JobOptions(cache_dir=args.cache_dir, refresh_cache=args.refresh_cache, chunk_size=args.chunk_size, pause_ms=args.pause_ms, repair_ocr=args.repair_ocr, dictionaries=tuple(args.dictionary), operations=tuple(args.apply),ipa_dictionaries=tuple(args.ipa_dictionary),language=args.language)

def _list_voices(engine_name: str, model: str, json_output: bool=False) -> None:
    engine = get_engine(engine_name, model)
    names = engine.voices()
    if engine.key == 'coqui' and model:
        from .neural_runtime import is_installed
        if is_installed('coqui'):
            names = engine.voices_for_model(model)
    if json_output:
        print(json.dumps({'engine': engine.key, 'voices': names}, ensure_ascii=False, indent=2))
    else:
        print(f'Engine: {engine.key} — {engine.label}')
        print('\n'.join(names) if names else 'No voice identifiers available. External models may be required.')

def _run_speech_command(args, *, output: str | None=None, raw: bool=False, stdout_wav: bool=False) -> None:
    settings = _settings(args)
    options = _options(args)
    engine = get_engine(args.engine, args.model)
    if settings.pitch and (not engine.supports_pitch) or (settings.rate and (not engine.supports_rate)):
        print(f'Notice: {engine.key} ignores unsupported pitch or rate settings.', file=sys.stderr)
    text = _load_input(args)
    status = ConsoleProgress()
    if raw or stdout_wav:
        with tempfile.TemporaryDirectory(prefix='openvoice-pipe-') as work:
            wav = Path(work) / 'output.wav'
            render_text(text, wav, engine, settings, options, status=status)
            if raw:
                write_raw_pcm(wav, sys.stdout.buffer)
            else:
                with wav.open('rb') as stream:
                    import shutil
                    shutil.copyfileobj(stream, sys.stdout.buffer)
            sys.stdout.buffer.flush()
    elif output:
        print(f'Saved: {render_text(text, output, engine, settings, options, status=status)}')
    else:
        speak_text(text, engine, settings, options, status=status)

def _batch(args) -> int:
    settings = _settings(args)
    options = _options(args)
    engine = None if args.dry_run else get_engine(args.engine, args.model)
    destination = Path(args.output_dir)
    failures = 0
    used = set()
    status = ConsoleProgress()
    for index, file in enumerate(args.files):
        path = Path(file)
        suffix = f'.{args.format}'
        dest = destination / (path.stem + suffix)
        number = 2
        while str(dest).lower() in used:
            dest = destination / f'{path.stem}-{number}{suffix}'
            number += 1
        used.add(str(dest).lower())
        if dest.exists() and args.skip_existing:
            print(f'Skipped: {dest}')
            continue
        if args.dry_run:
            print(f'Would convert: {path} -> {dest}')
            continue
        try:
            render_text(read_document(path), dest, engine, settings, options,
                        status=subprogress(status,.98*index/len(args.files),.98*(index+1)/len(args.files), f'File {index+1} of {len(args.files)}: {path.name}'))
            print(f'Saved: {dest}')
        except (OSError, ValueError, RuntimeError) as exc:
            failures += 1
            print(f'FAILED {path}: {exc}', file=sys.stderr)
    if not args.dry_run:
        emit(status,.99 if failures else 1, f'Batch finished with {failures} errors' if failures else 'All audio files saved',1)
    return 1 if failures else 0

def _voice_library_command(args) -> int:
    from .voice_library import VoiceLibrary, duplicate_models, export_voice_pack, import_voice_pack
    metadata = VoiceLibrary(args.metadata_file or None)
    action = args.action
    if action == 'list':
        result = metadata.list_voices(favorites_only=args.favorites, tag=args.tag)
    elif action in ('favorite', 'unfavorite'):
        if len(args.names) != 1:
            raise ValueError('Specify exactly one voice name')
        metadata.set_favorite(args.names[0], action == 'favorite')
        result = {'name': args.names[0], 'favorite': action == 'favorite'}
    elif action == 'tags':
        if len(args.names) != 1:
            raise ValueError('Specify exactly one voice name')
        metadata.set_tags(args.names[0], args.tags.split(','))
        result = {'name': args.names[0], 'tags': metadata.voices[args.names[0]]['tags']}
    elif action == 'collection':
        if len(args.names) < 2:
            raise ValueError('Usage: voice-library collection COLLECTION_NAME VOICE [VOICE ...]')
        metadata.set_collection(args.names[0], args.names[1:])
        result = {args.names[0]: metadata.collections[args.names[0]]}
    elif action == 'collections':
        result = metadata.collections
    elif action == 'duplicates':
        result = duplicate_models()
    elif action == 'export-pack':
        if not args.output or not args.names:
            raise ValueError('Usage: voice-library export-pack VOICE [VOICE ...] -w PACK.zip')
        result = {'saved': str(export_voice_pack(args.output, args.names))}
    elif action == 'import-pack':
        if len(args.names) != 1:
            raise ValueError('Usage: voice-library import-pack PACK.zip [--target DIR] [--overwrite]')
        result = {'installed': [str(p) for p in import_voice_pack(args.names[0], target=args.target, overwrite=args.overwrite)]}
    else:
        raise ValueError('Unknown voice-library operation')
    if args.json or isinstance(result, (list, dict)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
    return 0


def _library_command(args) -> int:
    from .project_library import ProjectLibrary, health_check
    library = ProjectLibrary(args.index)
    action = args.action
    if action == 'add':
        if not args.paths:
            raise ValueError('Pass at least one project file to add')
        tags = [t.strip() for t in args.tags.split(',') if t.strip()]
        for path in args.paths:
            entry = library.add(path, category=args.category or 'uncategorized',
                                tags=tags, favorite=args.favorites)
            print(f'Added: {entry.name} ({entry.path})')
        library.save()
        return 0
    if action == 'remove':
        for key in args.paths:
            print(f'Removed: {library.remove(key).name}')
        library.save()
        return 0
    if action == 'category':
        if len(args.paths) != 1 or not args.category:
            raise ValueError('Usage: library category PROJECT --category NAME')
        print(f'Category: {library.set_category(args.paths[0], args.category).category}')
        library.save()
        return 0
    if action == 'tags':
        if len(args.paths) != 1:
            raise ValueError('Usage: library tags PROJECT --tags a,b,c')
        tags = [t.strip() for t in args.tags.split(',') if t.strip()]
        print('Tags: ' + ', '.join(library.set_tags(args.paths[0], tags).tags))
        library.save()
        return 0
    if action == 'favorite':
        if len(args.paths) != 1:
            raise ValueError('Usage: library favorite PROJECT')
        entry = library.set_favorite(args.paths[0], not library.find(args.paths[0]).favorite)
        print(('Favorited: ' if entry.favorite else 'Unfavorited: ') + entry.name)
        library.save()
        return 0
    if action == 'note':
        if len(args.paths) != 1:
            raise ValueError('Usage: library note PROJECT --note TEXT')
        library.set_notes(args.paths[0], args.note)
        library.save()
        print('Note saved.')
        return 0
    if action == 'bookmark':
        if len(args.paths) != 2:
            raise ValueError('Usage: library bookmark PROJECT NAME [--note TEXT]')
        bookmark = library.add_bookmark(args.paths[0], args.paths[1], note=args.note)
        library.save()
        print(f'Bookmark saved: {bookmark.name}')
        return 0
    if action == 'rename':
        changes = library.batch_rename(args.pattern, args.replacement, regex=args.regex,
                                       dry_run=args.dry_run)
        for old, new in changes:
            print(f'{"Would rename" if args.dry_run else "Renamed"}: {old} -> {new}')
        if not args.dry_run:
            library.save()
        return 0
    if action == 'list':
        found = library.search(args.query, favorites_only=args.favorites)
    elif action == 'search':
        found = library.search(args.query, category=args.category,
                               tag=args.tags, favorites_only=args.favorites,
                               include_project_text=args.text_search)
    elif action == 'duplicates':
        groups = library.duplicates()
        if args.json:
            print(json.dumps([[e.path for e in g] for g in groups], indent=2))
        else:
            for group in groups:
                print('Duplicate set: ' + ' | '.join(e.path for e in group))
            if not groups:
                print('No duplicate projects found.')
        return 0
    elif action == 'storage':
        if len(args.paths) != 1:
            raise ValueError('Usage: library storage FOLDER')
        report = library.storage_analysis(args.paths[0])
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            for group, size in sorted(report['bytes_by_group'].items(), key=lambda kv: -kv[1]):
                print(f'{group:8} {size / 1048576:12.2f} MB')
            print(f"{'total':8} {report['total_bytes'] / 1048576:12.2f} MB ({report['files']} files)")
        return 0
    elif action == 'health':
        if not args.paths:
            raise ValueError('Pass project files to check')
        unhealthy = 0
        for path in args.paths:
            report = health_check(path)
            unhealthy += 0 if report['healthy'] else 1
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                state = 'healthy' if report['healthy'] else 'PROBLEMS: ' + '; '.join(report['problems'])
                print(f"{report['path']}: {state}" + (f" (warnings: {'; '.join(report['warnings'])})" if report['warnings'] else ''))
        return 1 if unhealthy else 0
    else:
        raise ValueError(f'Unknown library action: {action}')
    if args.json:
        print(json.dumps([e.to_dict() for e in found], ensure_ascii=False, indent=2))
    else:
        for entry in found:
            marker = '*' if entry.favorite else ' '
            tags = f' [{", ".join(entry.tags)}]' if entry.tags else ''
            print(f'{marker} {entry.name} — {entry.category}{tags} — {entry.path}')
        if not found:
            print('No matching projects.')
    return 0


def _chapters_command(args) -> int:
    from .book_structure import (detect_chapters, table_of_contents, detect_scene_breaks,
                                 detect_headers_footers, estimate_durations,
                                 set_status, completion_summary)
    if args.action in ('set-status', 'status-summary'):
        if not args.status_file:
            raise ValueError('Pass --status-file for status actions')
        if args.action == 'set-status':
            if not args.chapter or not args.status:
                raise ValueError('set-status needs --chapter and --status')
            set_status(args.status_file, args.chapter, args.status)
            print(f'{args.chapter}: {args.status}')
        else:
            summary = completion_summary(args.status_file)
            print(json.dumps(summary, indent=2) if args.json
                  else '; '.join(f'{k}: {v}' for k, v in summary.items()))
        return 0
    if not args.file:
        raise ValueError('Pass -f FILE with the manuscript')
    text = read_document(args.file)
    if args.action == 'detect':
        sections = detect_chapters(text, custom_rules=args.rule or None)
        data = [{'level': s.level, 'title': s.title, 'words': s.words()} for s in sections]
        print(json.dumps(data, ensure_ascii=False, indent=2) if args.json
              else '\n'.join(f"{d['title']} ({d['words']} words)" for d in data))
        return 0
    if args.action == 'toc':
        sections = detect_chapters(text, custom_rules=args.rule or None)
        print(table_of_contents(sections, style=args.style))
        return 0
    if args.action == 'scenes':
        breaks = detect_scene_breaks(text)
        print(json.dumps(breaks, indent=2) if args.json
              else '\n'.join(f"line {b['line']}: {b['marker']}" for b in breaks) or 'No scene breaks found.')
        return 0
    if args.action == 'headers':
        report = detect_headers_footers(text)
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else
              f"Pages: {report['pages']}; recurring headers: {len(report['headers'])}; footers: {len(report['footers'])}")
        return 0
    if args.action == 'estimate':
        sections = detect_chapters(text, custom_rules=args.rule or None)
        report = estimate_durations(sections, wpm=args.wpm)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for row in report['sections']:
                print(f"{row['title']}: {row['estimated_seconds'] / 60:.1f} min ({row['words']} words)")
            print(f"Total: {report['total_estimated_seconds'] / 3600:.2f} hours at {args.wpm} wpm")
        return 0
    raise ValueError(f'Unknown chapters action: {args.action}')


def _proofread_command(args) -> int:
    from .proofreading import (proper_name_consistency, dialogue_punctuation_issues,
                               ocr_punctuation_report, readability, terminology_consistency,
                               pronunciation_audit)
    texts = [(Path(f).stem, read_document(f)) for f in args.file]
    if args.action == 'terminology':
        report = terminology_consistency(dict(texts))
    elif args.action == 'readability':
        report = readability(texts[0][1])
    elif args.action == 'names':
        report = proper_name_consistency(texts[0][1])
    elif args.action == 'dialogue':
        report = dialogue_punctuation_issues(texts[0][1])
    elif args.action == 'ocr-artifacts':
        report = ocr_punctuation_report(texts[0][1])
    elif args.action == 'pronunciation-audit':
        dictionary = set()
        for path in args.dictionary:
            dictionary.update(w.strip() for w in Path(path).read_text(encoding='utf-8').splitlines() if w.strip())
        overrides = set()
        for path in args.overrides:
            if path.strip():
                from .ipa_pronunciation import load_pronunciations
                overrides.update(row.word for row in load_pronunciations([path]))
        report = pronunciation_audit(texts[0][1], dictionary_words=dictionary, override_words=overrides)
    else:
        raise ValueError(f'Unknown proofread action: {args.action}')
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output + '\n', encoding='utf-8')
        print(f'Saved: {args.output}')
    else:
        print(output)
    return 0


def _production_command(args) -> int:
    from .production import (ProductionBoard, ProductionLog, estimate_render_seconds,
                             forecast_resources)
    if args.action in ('estimate', 'forecast'):
        if not args.file:
            raise ValueError('Pass -f FILE with the manuscript')
        from .book_structure import detect_chapters
        sections = detect_chapters(read_document(args.file))
        if args.action == 'estimate':
            words = sum(s.words() for s in sections)
            report = estimate_render_seconds(words, realtime_factor=args.rtf, wpm=args.wpm)
        else:
            report = forecast_resources([{'title': s.title, 'words': s.words()} for s in sections],
                                        audio_format=args.format, wpm=args.wpm)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.action in ('log', 'log-summary'):
        if not args.log_file:
            raise ValueError('Pass --log-file for log actions')
        log = ProductionLog(args.log_file, redact=args.redact)
        if args.action == 'log':
            if not args.event:
                raise ValueError('Pass --event for the log action')
            fields = dict(item.split('=', 1) for item in args.detail)
            entry = log.record(args.event, level=args.level, **fields)
            print(json.dumps(entry, ensure_ascii=False))
        else:
            print(json.dumps(log.summary(), indent=2))
        return 0
    board = ProductionBoard(args.board)
    if args.action == 'dashboard':
        report = board.dashboard()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Chapters: {report['total_chapters']}; approved: {report['approved']}; "
                  f"exported: {report['exported']} ({report['percent_exported']}%)")
            for stage, count in report['chapters_by_stage'].items():
                print(f'  {stage:10} {count}')
        return 0
    if not args.chapter:
        raise ValueError('Pass --chapter for this action')
    if args.action == 'stage':
        if not args.stage:
            raise ValueError('Pass --stage for the stage action')
        board.set_stage(args.chapter, args.stage)
        print(f'{args.chapter}: {args.stage}')
    elif args.action == 'checkpoint':
        if not args.checkpoint:
            raise ValueError('Pass --checkpoint for the checkpoint action')
        board.set_checkpoint(args.chapter, args.checkpoint, args.passed)
        print(f'{args.chapter}: {args.checkpoint} = {"passed" if args.passed else "FAILED"}')
    elif args.action == 'approve':
        board.approve(args.chapter)
        print(f'{args.chapter}: approved')
    board.save()
    return 0


def main(argv: list[str] | None=None) -> int:
    from .desktop_prefs import activate
    activate()
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv[:1] in (['_gl-worker'],['_gl-probe']):
        from .legacy_gl import worker as gl_worker
        return gl_worker(probe_only=argv[0]=='_gl-probe',allow_software=argv==['_gl-probe','--software-test'])
    commands = {'studio','project-pack','project-unpack','project-render','project-verify','voice-catalog','voice-download','detect-language','character-profiles','multivoice','ipa-check','audiobooks', 'gui', 'engine-install', 'engines', 'voices', 'speak', 'render', 'batch', 'tools', 'transform', 'stats', 'split', 'audio-info', 'audio', 'video', 'media-tools'}
    commands.update({'read-along', 'subtitle-pack', 'audio-regression', 'publish-book', 'audio-quality', 'ocr', 'spellcheck', 'captions', 'release-archive', 'environment-sbom'})
    commands.update({'library', 'chapters', 'proofread', 'name-files', 'sample', 'release-notes',
                     'attribution', 'transcript', 'production', 'voice-library', 'script-check', 'publication-check', 'segment-audit', 'tag-audio', 'hardware-check'})
    if GUTENBERG_ENABLED:
        commands.add('gutenberg')
    try:
        if not GUTENBERG_ENABLED and argv and argv[0] == 'gutenberg':
            raise ValueError('Gutenberg Mode is not included in Version 1')
        if (argv and argv[0] in commands) or argv in (['--help'], ['-h'], ['--version']):
            args = make_parser().parse_args(argv)
            if getattr(args, 'performance_profile', ''):
                from .hardware import apply_cpu_profile
                apply_cpu_profile(args.performance_profile)
            if getattr(args, 'gpu', None) is not None:
                from .hardware import gpu_preference
                gpu_preference(args.gpu)
            if args.command == 'studio':
                from .studio_cli import run as run_studio
                return run_studio(args)
            if args.command == 'read-along':
                from .read_along import export_epub
                export_epub(args.audio, args.timing, args.output, args.title, args.language)
                return 0
            if args.command == 'subtitle-pack':
                from .release_tools import package_subtitles
                package_subtitles(args.output, args.tracks)
                return 0
            if args.command == 'audio-regression':
                from .release_tools import compare_recordings
                result = compare_recordings(args.reference, args.candidate, args.max_rms_error)
                print(json.dumps(result, indent=2))
                return 0 if result['passed'] else 1
            if args.command == 'hardware-check':
                from .hardware import hardware_status, apply_cpu_profile
                if args.profile:
                    apply_cpu_profile(args.profile)
                print(json.dumps(hardware_status(args.folder), ensure_ascii=False, indent=2))
                return 0
            if args.command == 'tag-audio':
                from .media_metadata import tag_audio
                values = {}
                for pair in args.tag:
                    if '=' not in pair:
                        raise ValueError('Metadata must use KEY=VALUE')
                    key, val = pair.split('=', 1)
                    values[key.strip()] = val
                print(f'Saved: {tag_audio(args.input, args.output, tags=values, cover=args.cover or None)}')
                return 0
            if args.command == 'voice-library':
                return _voice_library_command(args)
            if args.command in ('script-check', 'publication-check', 'segment-audit'):
                from .manuscript_validation import mixed_script_report, publication_preflight, audit_audio_segments
                if args.command == 'script-check':
                    report = mixed_script_report(read_document(args.file), max_issues=args.max_issues)
                elif args.command == 'publication-check':
                    report = publication_preflight(args.folder, title=args.title, author=args.author,
                                                   language=args.language, cover=args.cover)
                else:
                    report = audit_audio_segments(args.manifest, args.folder)
                output = json.dumps(report, ensure_ascii=False, indent=2)
                if args.output:
                    Path(args.output).write_text(output + '\n', encoding='utf-8')
                    print(f'Saved: {args.output}')
                else:
                    print(output)
                return 0
            if args.command == 'publish-book':
                from .release_tools import publish_book
                publish_book(args.manifest, args.output)
                return 0
            if args.command == 'audio-quality':
                from .release_tools import quality_report
                print(json.dumps(quality_report(args.file), indent=2))
                return 0
            if args.command in {'captions', 'release-archive', 'environment-sbom'}:
                from .release_tools import caption_export, release_archive, environment_inventory
                if args.command == 'captions':
                    if Path(args.output).suffix.lower() == '.ass':
                        from .publishing import ass_export
                        ass_export(args.source, args.output, font=args.font,
                                   size=args.font_size, alignment=args.alignment)
                        print(f'Saved: {args.output}')
                    else:
                        caption_export(args.source, args.output)
                elif args.command == 'release-archive':
                    release_archive(args.folder, args.output)
                else:
                    print(json.dumps(environment_inventory(), indent=2, ensure_ascii=False))
                return 0
            if args.command == 'library':
                return _library_command(args)
            if args.command == 'chapters':
                return _chapters_command(args)
            if args.command == 'proofread':
                return _proofread_command(args)
            if args.command == 'production':
                return _production_command(args)
            if args.command == 'name-files':
                from .publishing import name_chapters
                from datetime import date
                context = {'title': args.title, 'author': args.author, 'language': args.language,
                           'narrator': args.narrator, 'date': date.today().isoformat()}
                if not args.chapters:
                    raise ValueError('Pass chapter titles to name')
                for name in name_chapters(args.pattern, args.chapters, context):
                    print(name)
                return 0
            if args.command == 'sample':
                from .publishing import create_sample
                print(f'Saved: {create_sample(args.source, args.output, start=args.start, duration=args.duration, fade_seconds=args.fade_seconds)}')
                return 0
            if args.command == 'release-notes':
                from .publishing import release_notes
                changes = json.loads(Path(args.changes).read_text(encoding='utf-8'))
                if not isinstance(changes, list):
                    raise ValueError('Changes file must contain a JSON list')
                notes = release_notes(args.version, changes, title=args.title)
                if args.output:
                    Path(args.output).write_text(notes, encoding='utf-8')
                    print(f'Saved: {args.output}')
                else:
                    print(notes, end='')
                return 0
            if args.command == 'attribution':
                from .publishing import attribution_document
                assets = json.loads(Path(args.assets).read_text(encoding='utf-8'))
                if not isinstance(assets, list):
                    raise ValueError('Assets file must contain a JSON list')
                document = attribution_document(args.project, assets, author=args.author,
                                                narrator=args.narrator)
                if args.output:
                    Path(args.output).write_text(document, encoding='utf-8')
                    print(f'Saved: {args.output}')
                else:
                    print(document, end='')
                return 0
            if args.command == 'transcript':
                from .book_structure import detect_chapters
                from .publishing import export_transcript
                text = read_document(args.file)
                sections = detect_chapters(text, custom_rules=args.rule or None)
                title = args.title or Path(args.file).stem
                result = export_transcript(args.output, title,
                                           [(s.title, s.text) for s in sections], author=args.author)
                print(f'Saved: {result}')
                return 0
            if args.command == 'project-pack':
                voice = VoiceProject.load(args.voice_project) if args.voice_project else VoiceProject()
                project = ProjectData(text=read_document(args.file),voice_project=voice,
                                      current_filename=Path(args.file).name,
                                      settings={'engine':'auto','model':args.model,'ipa_dictionary':args.ipa_dictionary},
                                      video_images=[Path(x) for x in args.images])
                print(f'Saved: {save_project(args.output,project)}')
                return 0
            if args.command in ('project-unpack','project-render','project-verify'):
                with tempfile.TemporaryDirectory(prefix='openmukti-project-cli-') as temporary:
                    root=Path(args.output_dir) if args.command=='project-unpack' else Path(temporary)
                    saved=load_project(args.project,root)
                    if args.command == 'project-verify':
                        print(json.dumps({'valid':True,'characters':len(saved.voice_project.profiles),
                                          'books':len(saved.books),'chapters':sum(len(x.chapters) for x in saved.books),
                                          'image_count':len(saved.video_images)},indent=2))
                        return 0
                    if args.command == 'project-unpack':
                        (root/'project-text.txt').write_text(saved.text,encoding='utf-8')
                        saved.voice_project.save(root/'character-voices.json')
                        print(f'Project extracted: {root}')
                        return 0
                    settings=saved.settings
                    engine_name=settings.get('engine','auto')
                    speech=SpeechSettings(voice=settings.get('voice',''),model=settings.get('model',''),speaker_id=settings.get('speaker_id'),
                                         rate=int(settings.get('rate',0)),pitch=int(settings.get('pitch',0)),
                                         volume=int(settings.get('volume',100)), language=settings.get('language','auto'))
                    opts=JobOptions(repair_ocr=bool(settings.get('ocr',False)),
                                    dictionaries=(settings['dictionary'],) if settings.get('dictionary') else (),
                                    ipa_dictionaries=(settings['ipa_dictionary'],) if settings.get('ipa_dictionary') else ())
                    script=saved.text
                    if saved.active_character.casefold()!='narrator':
                        script=f'[{saved.active_character}] '+script
                    target=Path(args.output)
                    engine=get_engine(engine_name,speech.model)
                    status=ConsoleProgress()
                    if saved.use_character_voices:
                        if target.suffix.lower() in ('.mp4','.mkv','.mov','.webm') and saved.video_audio:
                            result=render_video(saved.video_images,target,audio=saved.video_audio,text=saved.text,video_options=VideoOptions(**saved.video_settings) if saved.video_settings else VideoOptions(),status=status)
                        elif target.suffix.lower() in ('.mp4','.mkv','.mov','.webm'):
                            if not saved.video_images and saved.video_settings.get('animation','none')=='none':
                                raise ValueError('Saved project has no video images. Select animated text mode for cover-free video.')
                            video_opts=VideoOptions(**saved.video_settings) if saved.video_settings else VideoOptions()
                            result=render_multivoice_video(script,saved.video_images,target,saved.voice_project,
                                            video_options=video_opts,default_engine=engine,default_settings=speech,speech_options=opts,status=status)
                        else:
                            result=render_multivoice(script,target,saved.voice_project,
                                            default_engine=engine,default_settings=speech,speech_options=opts,status=status)
                    else:
                        if target.suffix.lower() in ('.mp4','.mkv','.mov','.webm'):
                            result=render_video(saved.video_images,target,audio=saved.video_audio,text=saved.text,
                                                engine=engine,settings=speech,speech_options=opts,
                                                video_options=VideoOptions(**saved.video_settings) if saved.video_settings else VideoOptions(),status=status)
                        else:
                            result=render_text(saved.text,target,engine,speech,opts,status=status)
                    print(f'Saved: {result}')
                    return 0
            if args.command == 'gui':
                from .gui import main as launch
                return launch()
            if args.command == 'ocr':
                from .ocr import OCRSettings, import_ocr, ocr_status
                from .spelling import EnglishSpeller, apply_corrections
                if args.status:
                    print(json.dumps(ocr_status(), ensure_ascii=False, indent=2))
                    return 0
                if not args.source:
                    raise ValueError('Pass an OCR source file or folder, or use --status.')
                options = OCRSettings(enhance_blur=args.enhance_blur,historic_print=args.historic_print,language=args.language, dpi=args.dpi,
                    region=tuple(args.region or ()), corners=tuple(args.corners or ()),
                    preprocessing=args.preprocessing, contrast=args.contrast, psm=args.psm,
                    first_page=args.first_page, last_page=args.last_page, force_ocr=args.force_ocr,
                    split_spreads=args.split_spreads, denoise=not args.no_denoise,
                    deskew=not args.no_deskew, auto_rotate=not args.no_rotate)
                if args.searchable_pdf:
                    from .ocr import create_searchable_pdf
                    print(f'Saved searchable PDF: {create_searchable_pdf(args.source, args.searchable_pdf, options, progress=lambda page,total,label: print(label, file=sys.stderr))}', file=sys.stderr)
                    if not args.output and not args.json and not args.correct:
                        return 0
                result = import_ocr(args.source, options,
                    progress=lambda page,total,label: print(f'Page {page}: {label}', file=sys.stderr))
                content = result.text
                if args.correct:
                    checker = EnglishSpeller()
                    for page in result.pages:
                        page.text, _ = apply_corrections(page.text, checker.check(page.text, ocr=True))
                    content = result.text
                if args.json:
                    content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
                if args.output:
                    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                    Path(args.output).write_text(content, encoding='utf-8')
                else:
                    print(content)
                return 0
            if args.command == 'spellcheck':
                from dataclasses import asdict
                from .spelling import EnglishSpeller, apply_corrections
                checker = EnglishSpeller()
                original = read_document(args.file)
                issues = checker.check(original, ocr=True, check_names=args.check_names)
                content, count = apply_corrections(original, issues, safe_only=args.safe_only) if args.correct else (original, 0)
                if args.output:
                    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                    Path(args.output).write_text(content, encoding='utf-8')
                if args.json:
                    print(json.dumps({'issues': [asdict(i) for i in issues], 'corrections': count, 'text': content}, ensure_ascii=False, indent=2))
                elif args.correct and not args.output:
                    print(content)
                else:
                    print(f'{len(issues)} issues; {count} corrections applied.')
                return 0
            if args.command == 'engine-install':
                from .neural_runtime import ensure_installed, NEURAL_ENGINES
                targets = NEURAL_ENGINES if args.engine == 'all' else (args.engine,)
                for name in targets:
                    print(f'Installing {name} CPU dependencies...', flush=True)
                    python = ensure_installed(name, report=lambda message: print(message, flush=True))
                    print(f'Installed {name}: {python}', flush=True)
                print('No model weights were downloaded. Open the GUI Voices → Download Kokoro / Kitten / Pocket / Coqui voices to choose and download model assets explicitly.', flush=True)
                return 0
            if args.command == 'engines':
                items = [{'key': key, 'available': engine.available(), 'label': engine.label} for key, engine in all_engines().items()]
                print(json.dumps(items, indent=2) if args.json else '\n'.join((f"{v['key']:10} {('available' if v['available'] else 'unavailable'):11} {v['label']}" for v in items)))
                return 0
            if args.command == 'voices':
                if args.speakers:
                    targets = [args.model] if args.model else [v.name for v in discover_voices()]
                    speakers = {name: [{'id': sp.id, 'name': sp.name, 'label': sp.label}
                                       for sp in speaker_list(name)] for name in targets}
                    if args.json:
                        print(json.dumps(speakers, indent=2, ensure_ascii=False))
                    else:
                        for name, values in speakers.items():
                            print(name + ':')
                            for item in values:
                                print('  ' + item['label'])
                        if not targets:
                            print('No installed Piper voices; choose --model /path/to/voice.onnx')
                else:
                    _list_voices(args.engine, args.model, args.json)
                return 0
            if args.command == 'tools':
                matches = [t for t in TOOLS.values() if not args.group or args.group.casefold() in t.group.casefold()]
                print(json.dumps([{'id': t.name, 'title': t.title, 'group': t.group} for t in matches], indent=2) if args.json else '\n'.join((f'{t.name:34} {t.title} ({t.group})' for t in matches)))
                return 0
            if args.command == 'transform':
                result = transform(_load_input(args), args.apply)
                if args.output:
                    path = Path(args.output)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(result, encoding='utf-8')
                    print(f'Saved: {path}')
                else:
                    print(result)
                return 0
            if args.command == 'stats':
                data = text_stats(_load_input(args), args.wpm)
                print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else '\n'.join((f'{key}: {value}' for key, value in data.items())))
                return 0
            if args.command == 'split':
                from .processing import split_text
                from .texttools import split_sentences
                segments = split_sentences(_load_input(args)) if args.sentences else split_text(_load_input(args), args.chunk_size)
                print(json.dumps(segments, ensure_ascii=False, indent=2) if args.json else '\n\n'.join(segments))
                return 0
            if args.command == 'media-tools':
                status = media_tools_status()
                if args.json:
                    print(json.dumps(status, ensure_ascii=False, indent=2))
                else:
                    for key, value in status.items():
                        state = 'integrated' if value['bundled'] else ('system fallback' if value['available'] else 'not available')
                        print(f"{key}: {state} | {value['version']} | {value['path']}")
                return 0 if all(item['available'] for item in status.values()) else 1
            if args.command == 'audio-info':
                print(json.dumps(audio_info(args.input), ensure_ascii=False, indent=2))
                return 0
            if args.command == 'audio':
                result = process_audio(args.inputs, args.output, operation=args.operation, start=args.start, duration=args.duration, speed=args.speed, gain=args.gain, sample_rate=args.sample_rate, channels=args.channels, fade_seconds=args.fade_seconds, compression=args.compression, eq_frequency=args.eq_frequency, eq_gain=args.eq_gain, pan=args.pan, silence_db=args.silence_db, silence_duration=args.silence_duration, status=ConsoleProgress())
                print(f'Saved: {result}')
                return 0
            if GUTENBERG_ENABLED and args.command == 'gutenberg':
                from .gutenberg import split_chapters
                output = Path(args.output_dir)
                output.mkdir(parents=True, exist_ok=True)
                results = []
                for file in args.files:
                    try:
                        result = clean_gutenberg(read_document(file), GutenbergOptions(remove_toc=not args.keep_toc, remove_image_placeholders=not args.keep_placeholders, remove_page_numbers=not args.keep_page_numbers, reflow_paragraphs=not args.no_reflow))
                        stem = Path(file).stem
                        destination = output / f'{stem}-cleaned.txt'
                        destination.write_text(result.content, encoding='utf-8')
                        if args.split_chapters:
                            folder = output / (stem + '-chapters')
                            folder.mkdir(exist_ok=True)
                            for n, (title, content) in enumerate(split_chapters(result.content), 1):
                                (folder / f'{n:04d}.txt').write_text(content, encoding='utf-8')
                        results.append({'file':file, 'output':str(destination),'chapters':result.chapter_count,'removed_header':result.removed_header,'removed_footer':result.removed_footer,'removed_toc':result.removed_toc,'placeholders':result.removed_placeholders})
                    except (OSError, ValueError, RuntimeError) as exc:
                        results.append({'file': file, 'error':str(exc)})
                if args.json:
                    print(json.dumps(results, indent=2))
                else:
                    for r in results:
                        print('FAILED' if 'error' in r else 'Saved', r)
                return 1 if any('error' in r for r in results) else 0
            if args.command == 'voice-catalog':
                catalog=fetch_catalog(force=args.refresh)
                found=[v for v in catalog if not args.language or args.language.casefold() in (v.language+' '+v.language_name).casefold()]
                if args.json:
                    from dataclasses import asdict
                    print(json.dumps([asdict(v) for v in found],indent=2,ensure_ascii=False))
                else:
                    for v in found:
                        print(f'{v.language_name:16} {v.language:8} {v.key:36} {v.quality:8} {(v.model_bytes+v.config_bytes)/1048576:7.1f} MB')
                    print(f'{len(found)} voices')
                return 0
            if args.command == 'voice-download':
                catalog=fetch_catalog(force=args.refresh)
                selected=[v for v in catalog if v.key in args.models]
                if len(selected)!=len(set(args.models)):
                    missing=set(args.models)-{v.key for v in selected}
                    raise ValueError(f'Unknown voice models: {sorted(missing)}')
                if args.all:
                    selected=[v for v in catalog if not args.language or args.language.casefold() in (v.language+' '+v.language_name).casefold()]
                if not selected:
                    raise ValueError('No voices selected')
                size=voice_download_size(selected)
                if not args.yes:
                    if not sys.stdin.isatty():
                        raise ValueError('Pass --yes to confirm large downloads in non-interactive usage')
                    print(f'Download {len(selected)} models; estimated {size/1048576:,.1f} MB? [y/N] ',end='',flush=True)
                    if input().lower() not in ('y','yes'):
                        return 1
                result=download_selected(selected,progress=lambda n,total,key:print(f'{n}/{total} {key}',file=sys.stderr))
                for path in result:
                    print(path)
                return 0
            if args.command == 'ipa-check':
                from .ipa_pronunciation import load_pronunciations,language_matches
                rows=load_pronunciations(args.dictionary)
                matched=[row for row in rows if args.language=='*' or language_matches(row.language,args.language)]
                print(json.dumps([row.__dict__ for row in matched],ensure_ascii=False,indent=2))
                return 0
            if args.command == 'detect-language':
                content=_load_input(args)
                data=detected_languages(content)
                if args.json:
                    print(json.dumps(data,ensure_ascii=False))
                else:
                    for language,confidence in data:
                        print(f'{language}: heuristic confidence {confidence:.2f}')
                return 0
            if args.command == 'character-profiles':
                content=_load_input(args)
                existing=VoiceProject.load(args.update_project) if args.update_project else VoiceProject()
                names=[n for path in args.names for n in read_name_list(path)]
                project=auto_profiles(content,installed=discover_voices(),existing_profiles=existing.profiles,extra_names=names)
                project.profiles=merge_auto_profiles(existing.profiles,project.profiles)
                project.pronunciation_files=existing.pronunciation_files
                project.save(args.output)
                if args.report:
                    from dataclasses import asdict
                    report={'characters':[asdict(p) for p in project.profiles],'aliases':project.analysis.aliases,'quotations':[asdict(q) for q in project.analysis.quotations]}
                    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                print(f'Saved {len(project.profiles)} voice profiles: {args.output}')
                return 0
            if args.command == 'multivoice':
                project=VoiceProject.load(args.project)
                project.pronunciation_files.extend(args.ipa_dictionary)
                script=_load_input(args) if any([args.text,args.text_args,args.file,args.stdin]) else project.script
                if not script.strip():
                    raise ValueError('Voice project does not contain a script')
                if Path(args.output).suffix.lower() in {'.mp4','.mkv','.mov','.webm'}:
                    if not args.images:
                        raise ValueError('--images is required for multivoice video')
                    result=render_multivoice_video(script,args.images,args.output,project,video_options=VideoOptions(aspect=args.aspect,resolution=args.resolution,animation=args.animation,dimensions=args.dimensions,font_path=args.font_file,font_size=args.font_size,timing_file=args.timing_file,text_color=args.text_color,panel_opacity=args.panel_opacity,pen_width=args.pen_width,nib_angle=args.nib_angle,stroke_library=args.stroke_library,strict_strokes=args.strict_strokes,paper_grain=args.paper_grain,brush_dryness=args.brush_dryness,pen_tool=args.pen_tool),auto_tag=args.auto_tag,speech_options=JobOptions(cache_dir=args.cache_dir),status=ConsoleProgress())
                else:
                    result=render_multivoice(script,args.output,project,auto_tag=args.auto_tag,speech_options=JobOptions(cache_dir=args.cache_dir),status=ConsoleProgress())
                print(f'Saved: {result}')
                return 0
            if args.command == 'audiobooks':
                imported = load_manifest(args.manifest, gutenberg=getattr(args, 'gutenberg', False)) if args.manifest else discover_books(args.folder, gutenberg=getattr(args, 'gutenberg', False))
                missing_voice = any(c.audio is None for book in imported for c in book.chapters)
                engine = get_engine(args.engine, args.model) if missing_voice and not args.dry_run else None
                video_options = VideoOptions(aspect=args.aspect, resolution=args.resolution, fps=args.fps, fit=args.fit, captions=args.captions, crf=args.crf,animation=args.animation,dimensions=args.dimensions,font_path=args.font_file,font_size=args.font_size,timing_file=args.timing_file,text_color=args.text_color,panel_opacity=args.panel_opacity,pen_width=args.pen_width,nib_angle=args.nib_angle,stroke_library=args.stroke_library,strict_strokes=args.strict_strokes,paper_grain=args.paper_grain,brush_dryness=args.brush_dryness,pen_tool=args.pen_tool)
                opts = BookExportOptions(mode=args.mode, video=video_options, gutenberg=getattr(args, 'gutenberg', False), skip_existing=args.skip_existing, continue_on_error=not args.fail_fast, video_format=args.format,output_type=args.output_type,audio_format=args.audio_format)
                report = export_books(imported, args.output_dir, engine=engine, settings=_settings(args) if missing_voice and not args.dry_run else None, speech_options=_options(args), options=opts, voice_project=VoiceProject.load(args.voices_project) if args.voices_project else None,dry_run=args.dry_run, status=None if args.json else ConsoleProgress())
                if args.json:
                    print(json.dumps(report, ensure_ascii=False, indent=2))
                else:
                    print(f'Processed {len(report["books"])} books; {len(report["outputs"])} outputs; {len(report["failures"])} errors. Report: {Path(args.output_dir) / "openvoice-batch-report.json"}')
                    for error in report['failures']:
                        print(f'ERROR {error}', file=sys.stderr)
                return 1 if report['failures'] else 0
            if args.command == 'video':
                opts = VideoOptions(storyboard=args.storyboard,safe_margin=args.safe_margin,caption_preset=args.caption_preset,aspect=args.aspect, resolution=args.resolution, fps=args.fps, fit=args.fit, background=args.background, captions=args.captions, crf=args.crf,animation=args.animation,dimensions=args.dimensions,font_path=args.font_file,font_size=args.font_size,timing_file=args.timing_file,text_color=args.text_color,panel_opacity=args.panel_opacity,pen_width=args.pen_width,nib_angle=args.nib_angle,stroke_library=args.stroke_library,strict_strokes=args.strict_strokes,paper_grain=args.paper_grain,brush_dryness=args.brush_dryness,pen_tool=args.pen_tool)
                supplied = bool(args.text or args.text_args or args.file or args.stdin)
                narration = _load_input(args) if (not args.audio or supplied or ((args.captions or args.animation!='none') and not args.timing_file)) else ''
                engine = get_engine(args.engine, args.model) if not args.audio else None
                result = render_video(args.images, args.output, audio=args.audio, text=narration, engine=engine, settings=_settings(args) if not args.audio else None, speech_options=_options(args), video_options=opts,status=ConsoleProgress())
                print(f'Saved: {result}')
                if opts.captions:
                    print(f'Captions: {result.with_suffix(".srt")}')
                return 0
            if args.command == 'speak':
                _run_speech_command(args)
                return 0
            if args.command == 'render':
                _run_speech_command(args, output=args.output)
                return 0
            if args.command == 'batch':
                return _batch(args)
        elif not argv or argv == ['--gui']:
            from .gui import main as launch
            return launch()
        else:
            args = make_legacy_parser().parse_args(argv)
            if args.list_voices:
                _list_voices(args.engine, args.model)
                return 0
            if args.raw_stdout and args.stdout_wav:
                raise ValueError('Choose either -o or --stdout-wav')
            if args.output and (args.raw_stdout or args.stdout_wav):
                raise ValueError('Cannot combine -w with stdout audio')
            _run_speech_command(args, output=args.output, raw=args.raw_stdout, stdout_wav=args.stdout_wav)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, sqlite3.Error, zipfile.BadZipFile, subprocess.SubprocessError, ImportError) as exc:
        print(f'{APP_NAME} error: {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nCancelled.', file=sys.stderr)
        return 130
if __name__ == '__main__':
    raise SystemExit(main())
