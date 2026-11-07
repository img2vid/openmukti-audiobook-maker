"""CPU-only page OCR with bounded input, preprocessing and cancellable Tesseract.

Quality choices follow tesseract-ocr/tessdoc/ImproveQuality.md. OCR spelling
restoration is deliberately a separate, undoable editor operation.
"""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

from .documents import DocumentError

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp', '.pnm', '.pgm', '.ppm'}
SCAN_EXTENSIONS = IMAGE_EXTENSIONS | {'.pdf', '.zip', '.cbz'}
MAX_PAGE_BYTES = 80 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_INPUT_PIXELS = 60_000_000
MAX_WORK_PIXELS = 24_000_000
MAX_TEXT_CHARS = 20_000_000
PAGE_SEPARATOR = '\n\n\f\n\n'


class OCRError(DocumentError):
    pass


class OCRCancelled(OCRError):
    pass


@dataclass(frozen=True)
class OCRSettings:
    language: str = 'eng'
    dpi: int = 300
    preprocessing: str = 'auto'
    contrast: float = 1.4
    denoise: bool = True
    deskew: bool = True
    auto_rotate: bool = True
    split_spreads: bool = False
    psm: int = 3
    force_ocr: bool = False
    first_page: int = 1
    last_page: int = 0
    max_pages: int = 3000
    timeout: int = 120
    region: tuple[int, ...] = ()
    corners: tuple[int, ...] = ()
    enhance_blur: bool = False
    historic_print: bool = False

    def validate(self):
        if self.region and self.corners:
            raise OCRError('Choose either a rectangular region or perspective corners.')
        for values, count in ((self.region, 4), (self.corners, 8)):
            if values and (len(values) != count or any(type(v) is not int or v < 0 for v in values)):
                raise OCRError('Page coordinates must be nonnegative integers.')
        if (self.region or self.corners) and self.split_spreads:
            raise OCRError('Select a page region or split spreads separately.')
        if not re.fullmatch(r'(?:script/)?[A-Za-z0-9_]+(?:\+(?:script/)?[A-Za-z0-9_]+)*', self.language):
            raise OCRError('Use Tesseract language codes, such as eng or eng+hin.')
        if self.preprocessing not in {'auto', 'original', 'contrast', 'otsu', 'adaptive'}:
            raise OCRError('Unknown OCR preprocessing mode.')
        if not 100 <= self.dpi <= 600 or not .5 <= self.contrast <= 3:
            raise OCRError('OCR DPI must be 100–600 and contrast 0.5–3.0.')
        if self.psm not in {3, 4, 6, 11, 12}:
            raise OCRError('Page segmentation must be 3, 4, 6, 11 or 12.')
        if self.first_page < 1 or self.last_page < 0 or (self.last_page and self.last_page < self.first_page):
            raise OCRError('Invalid OCR page range; use 0 for the final page to read all pages.')
        if not 1 <= self.max_pages <= 10000 or not 5 <= self.timeout <= 600:
            raise OCRError('Invalid page limit or OCR timeout.')


@dataclass
class OCRPage:
    number: int
    source: str
    text: str
    confidence: float | None = None
    used_ocr: bool = True
    preprocessing: str = ''


@dataclass
class OCRResult:
    pages: list[OCRPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self):
        return PAGE_SEPARATOR.join(p.text for p in self.pages)

    @property
    def confidence(self):
        values = [p.confidence for p in self.pages if p.confidence is not None and p.text.strip()]
        return sum(values) / len(values) if values else None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls([OCRPage(**p) for p in data['pages']], data.get('warnings', []))


def natural_key(value):
    return [(1, int(p)) if p.isdigit() else (0, p.casefold()) for p in re.split(r'(\d+)', str(value))]


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise OCRCancelled('OCR cancelled. No partial text was applied.')


def find_tesseract():
    name = 'tesseract.exe' if os.name == 'nt' else 'tesseract'
    override = os.environ.get('OPENMUKTI_TESSERACT', '').strip()
    candidates = [Path(override).expanduser()] if override else []
    for base in (getattr(sys, '_MEIPASS', ''), Path(sys.executable).parent, Path(__file__).resolve().parent.parent):
        if base:
            candidates.extend([Path(base) / 'tesseract' / name, Path(base) / 'vendor' / 'tesseract' / name])
    if shutil.which(name):
        candidates.append(Path(shutil.which(name)))
    if os.name == 'nt':
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            if os.environ.get(key):
                candidates.append(Path(os.environ[key]) / 'Tesseract-OCR' / name)
    return next((p.resolve() for p in candidates if p.is_file()), None)


def _run(command, *, timeout=120, cancel=None):
    env = os.environ.copy()
    env.setdefault('OMP_THREAD_LIMIT', '2')
    options = {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'env': env}
    if os.name == 'nt':
        options['creationflags'] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen([str(x) for x in command], **options)
    except OSError as exc:
        raise OCRError(f'Cannot start OCR: {exc}') from exc
    deadline = time.monotonic() + timeout
    try:
        while True:
            _check_cancel(cancel)
            if time.monotonic() > deadline:
                raise OCRError(f'OCR page exceeded its {timeout}-second limit. Try a lower DPI.')
            try:
                out, err = proc.communicate(timeout=.15)
                return proc.returncode, out.decode('utf-8-sig', 'replace'), err.decode('utf-8', 'replace')
            except subprocess.TimeoutExpired:
                pass
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def _tool_args(binary):
    args = []
    data = Path(binary).parent / 'tessdata'
    if data.is_dir():
        args += ['--tessdata-dir', str(data)]
    return args


def ocr_status():
    binary = find_tesseract()
    if not binary:
        return {'available': False, 'languages': [], 'message': 'Install Tesseract 5 with eng and osd language data, or use the OCR-enabled portable Windows build.'}
    code, out, err = _run([binary, '--list-langs', *_tool_args(binary)], timeout=15)
    langs = [line.strip() for line in out.splitlines() if re.fullmatch(r'[A-Za-z0-9_/-]+', line.strip())]
    return {'available': code == 0, 'languages': langs, 'message': err.strip(), 'executable': str(binary)}


def _image_modules():
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        import numpy as np
    except ImportError as exc:
        raise OCRError('Image processing requires Pillow and NumPy (pip install ".[ocr]").') from exc
    # Certain OpenCV wheels fail to import on older systems even though Pillow
    # and Tesseract work. Original/contrast OCR must remain functional.
    try:
        import cv2
    except (ImportError, AttributeError, OSError):
        cv2 = None
    return Image, ImageEnhance, ImageFilter, ImageOps, np, cv2


def _cv_filter(cv, operation, array, *args, **kwargs):
    from .acceleration import gpu_enabled
    if gpu_enabled():
        try:
            if cv.ocl.haveOpenCL():
                cv.ocl.setUseOpenCL(True)
                if cv.ocl.useOpenCL():
                    result = operation(cv.UMat(array), *args, **kwargs)
                    if isinstance(result, tuple):
                        return result[0], result[1].get()
                    return result.get()
        except (cv.error, AttributeError, RuntimeError):
            pass
    return operation(array, *args, **kwargs)


def preprocess_image(image, settings: OCRSettings, *, mode=None):
    """Return dark text on white, preserving faint text in contrast mode."""
    Image, ImageEnhance, ImageFilter, ImageOps, np, cv = _image_modules()
    mode = mode or settings.preprocessing
    image = ImageOps.exif_transpose(image).convert('RGBA')
    white = Image.new('RGBA', image.size, 'white')
    white.alpha_composite(image)
    image = white.convert('L')
    if image.width * image.height > MAX_WORK_PIXELS:
        ratio = (MAX_WORK_PIXELS / (image.width * image.height)) ** .5
        image = image.resize((max(1, int(image.width * ratio)), max(1, int(image.height * ratio))), Image.Resampling.LANCZOS)
    elif min(image.size) < 1000 and max(image.size) < 2200:
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    if settings.enhance_blur:
        from .advanced_ocr import sharpen_if_blurred
        image,_,_=sharpen_if_blurred(image)
    if mode == 'original':
        return ImageOps.expand(image, border=12, fill=255)
    image = ImageOps.autocontrast(image, cutoff=.5)
    array = np.asarray(image)
    border = np.concatenate((array[0], array[-1], array[:, 0], array[:, -1]))
    if float(np.median(border)) < 100:
        array = 255 - array
    if settings.denoise:
        array = _cv_filter(cv, cv.medianBlur, array, 3) if cv is not None else np.asarray(Image.fromarray(array).filter(ImageFilter.MedianFilter(size=3)))
    if settings.deskew and cv is not None:
        # Projection profiles avoid the 90-degree ambiguity of minAreaRect.
        sample = cv.resize(array, (0, 0), fx=min(1, 1200 / array.shape[1]), fy=min(1, 1200 / array.shape[1]))
        _, ink = cv.threshold(sample, 0, 255, cv.THRESH_BINARY_INV + cv.THRESH_OTSU)
        center = (ink.shape[1] / 2, ink.shape[0] / 2)
        def score(angle):
            matrix = cv.getRotationMatrix2D(center, float(angle), 1)
            turned = cv.warpAffine(ink, matrix, (ink.shape[1], ink.shape[0]), flags=cv.INTER_NEAREST)
            profile = np.sum(turned, axis=1, dtype=np.float64)
            return float(np.sum(np.diff(profile) ** 2))
        angles = np.arange(-5, 5.01, .5)
        best = float(max(angles, key=score))
        if abs(best) >= .5 and score(best) > score(0) * 1.08:
            matrix = cv.getRotationMatrix2D((array.shape[1] / 2, array.shape[0] / 2), best, 1)
            array = _cv_filter(cv, cv.warpAffine, array, matrix, (array.shape[1], array.shape[0]), borderValue=255, flags=cv.INTER_CUBIC)
    image = ImageEnhance.Contrast(Image.fromarray(array)).enhance(settings.contrast)
    array = np.asarray(image)
    if mode in {'adaptive', 'auto'}:
        # Use PIL's deterministic threshold as a limited fallback when OpenCV
        # is not importable; this is not equivalent to adaptive thresholding.
        array = (_cv_filter(cv, cv.adaptiveThreshold, array, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 41, 13)
                 if cv is not None else np.asarray(Image.fromarray(array).point(lambda x: 255 if x >= 150 else 0)))
    elif mode == 'otsu':
        if cv is not None:
            _, array = _cv_filter(cv, cv.threshold, array, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        else:
            array = np.asarray(Image.fromarray(array).point(lambda x: 255 if x >= 150 else 0))
    return ImageOps.expand(Image.fromarray(array), border=18, fill=255)


def parse_tsv(source):
    lines, weights = [], []
    current, words = None, []
    reader = csv.DictReader(io.StringIO(source), delimiter='\t', quoting=csv.QUOTE_NONE)
    required = {'level', 'page_num', 'block_num', 'par_num', 'line_num', 'conf', 'text'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise OCRError('Tesseract did not return TSV word data. Its output configuration is invalid; ordinary text cannot be parsed as OCR confidence data.')
    for row in reader:
        if row.get('level') != '5' or not (row.get('text') or '').strip():
            continue
        key = (row.get('page_num'), row.get('block_num'), row.get('par_num'), row.get('line_num'))
        if current is not None and key != current:
            lines.append((' '.join(words), current[:3]))
            words = []
        current = key
        word = row['text'].strip()
        words.append(word)
        try:
            conf = float(row['conf'])
            if conf >= 0:
                weights.append((conf, len(word)))
        except (KeyError, ValueError, TypeError):
            pass
    if words:
        lines.append((' '.join(words), current[:3]))
    text, previous = '', None
    for line, paragraph in lines:
        if text:
            text += '\n\n' if paragraph != previous else '\n'
        text += line
        previous = paragraph
    confidence = sum(c * n for c, n in weights) / sum(n for _, n in weights) if weights else 0.0
    return text, round(confidence, 2)


def select_page_area(image, settings):
    """Coordinates refer to the EXIF-oriented raster, before deskew and scaling."""
    from PIL import ImageOps
    image = ImageOps.exif_transpose(image)
    if settings.region:
        x, y, right, bottom = settings.region
        if not (0 <= x < right <= image.width and 0 <= y < bottom <= image.height):
            raise OCRError('Selected rectangle is outside the page or has zero area.')
        return image.crop(settings.region)
    if settings.corners:
        import math
        Image, _, _, _, np, _ = _image_modules()
        points = list(zip(settings.corners[::2], settings.corners[1::2]))
        if any(x >= image.width or y >= image.height for x, y in points):
            raise OCRError('Perspective corners must be inside the page.')
        def clockwise(i):
            x, y = points[i]
            x1, y1 = points[(i+1) % 4]
            x2, y2 = points[(i+2) % 4]
            return (x1-x)*(y2-y1) - (y1-y)*(x2-x1) > 0
        if not all(clockwise(i) for i in range(4)):
            raise OCRError('Select four convex corners clockwise starting at top left.')
        a, b, c, d = points
        w = round(max(math.dist(a,b), math.dist(c,d))) + 1
        h = round(max(math.dist(b,c), math.dist(d,a))) + 1
        if min(w,h) < 2 or w*h > MAX_WORK_PIXELS:
            raise OCRError('Corrected page is too small or exceeds the processing limit.')
        # Pillow samples the input at coordinates mapped from each output pixel.
        matrix, values = [], []
        for (x, y), (u, v) in zip([(0,0), (w-1,0), (w-1,h-1), (0,h-1)], points):
            matrix.extend(((x,y,1,0,0,0,-u*x,-u*y), (0,0,0,x,y,1,-v*x,-v*y)))
            values.extend((u, v))
        coeffs = np.linalg.solve(matrix, values)
        return image.convert('RGBA').transform((w,h), Image.Transform.PERSPECTIVE,
                                               coeffs, resample=Image.Resampling.BICUBIC)
    return image


def recognize_page(image, settings: OCRSettings, *, cancel=None):
    settings.validate()
    binary = find_tesseract()
    if binary is None:
        raise OCRError(ocr_status()['message'])
    Image, _, _, ImageOps, _, _ = _image_modules()
    # Apply a phone/camera's orientation metadata before OSD, so the later
    # preprocessing stage cannot apply EXIF rotation a second time.
    image = select_page_area(image, settings)
    if image.mode == 'RGBA' or 'transparency' in image.info:
        rgba = image.convert('RGBA')
        flat = Image.new('RGBA', rgba.size, 'white')
        flat.alpha_composite(rgba)
        image = flat.convert('RGB')
    with tempfile.TemporaryDirectory(prefix='openmukti-ocr-') as temp:
        temp = Path(temp)
        if settings.auto_rotate:
            original = temp / 'orientation.png'
            image.save(original)
            code, out, _ = _run([binary, original, 'stdout', '-l', 'osd', '--psm', '0', *_tool_args(binary)], timeout=min(30, settings.timeout), cancel=cancel)
            if code == 0:
                rotation = re.search(r'Rotate:\s*(90|180|270)\b', out)
                confidence = re.search(r'Orientation confidence:\s*([\d.]+)', out)
                if rotation and confidence and float(confidence[1]) >= 2:
                    image = image.rotate(-int(rotation[1]), expand=True, fillcolor='white')
        modes = [settings.preprocessing]
        if settings.preprocessing == 'auto':
            modes = ['adaptive', 'contrast']
        results = []
        for mode in modes:
            _check_cancel(cancel)
            processed = preprocess_image(image, settings, mode=mode)
            source = temp / f'{mode}.png'
            processed.save(source, dpi=(settings.dpi, settings.dpi))
            # A named "tsv" config is optional in portable distributions.
            # Set the renderer parameters directly instead of relying on it.
            code, out, err = _run([binary, source, 'stdout', '-l', settings.language, '--oem', '1', '--psm', str(settings.psm), '--dpi', str(settings.dpi), *_tool_args(binary), '-c', 'tessedit_create_tsv=1', '-c', 'tessedit_create_txt=0'], timeout=settings.timeout, cancel=cancel)
            if code:
                raise OCRError('Tesseract failed: ' + (err.strip() or 'no diagnostic message')[:1200])
            try:
                text, conf = parse_tsv(out)
                if settings.historic_print:
                    from .advanced_ocr import historical
                    text=historical(text)
            except OCRError as exc:
                if err.strip():
                    raise OCRError(f'{exc} Tesseract diagnostic: {err.strip()[:1000]}') from exc
                raise
            results.append((text, conf, mode))
            if text and conf >= 88:
                break
        # Penalize an empty or suspiciously tiny high-confidence alternative.
        most = max(len(t.split()) for t, _, _ in results)
        return max(results, key=lambda r: r[1] * min(1, len(r[0].split()) / max(1, most * .8)))


def _safe_image_frames(source):
    Image, *_ = _image_modules()
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        try:
            with Image.open(source) as image:
                if image.width * image.height > MAX_INPUT_PIXELS:
                    raise OCRError('Image exceeds the 60-megapixel page limit. Resize it first.')
                for frame in range(getattr(image, 'n_frames', 1)):
                    image.seek(frame)
                    if image.width * image.height > MAX_INPUT_PIXELS:
                        raise OCRError('Image frame exceeds the 60-megapixel page limit.')
                    yield image.copy(), frame + 1
        except (Image.DecompressionBombWarning, Image.DecompressionBombError, OSError) as exc:
            raise OCRError(f'Cannot decode scan image: {exc}') from exc


def _pdf_pages(path, settings, cancel):
    try:
        import pypdfium2 as pdfium
    except (ImportError, OSError):
        # Poppler is available on BSD/Solaris and architectures without PDFium wheels.
        yield from _poppler_pdf_pages(path, settings, cancel)
        return
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception as exc:
        raise OCRError(f'Cannot open PDF (is it encrypted or damaged?): {exc}') from exc
    try:
        if len(document) > settings.max_pages and not settings.last_page:
            raise OCRError(f'PDF has more than {settings.max_pages} pages. Select a page range.')
        for index in range(len(document)):
            _check_cancel(cancel)
            if index + 1 < settings.first_page or (settings.last_page and index + 1 > settings.last_page):
                continue
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range().replace('\r\n', '\n').strip()
                finally:
                    textpage.close()
                # Each page is assessed independently so mixed PDFs retain text.
                usable = len(re.findall(r'[^\W\d_]', text)) >= 25 and text.count('\ufffd') < max(1, len(text) // 100)
                if usable and not (settings.force_ocr or settings.region or settings.corners):
                    yield index + 1, text, None
                else:
                    width, height = page.get_size()
                    scale = min(settings.dpi / 72, (MAX_WORK_PIXELS / max(1, width * height)) ** .5)
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil().copy()
                    finally:
                        bitmap.close()
                    yield index + 1, '', image
            finally:
                page.close()
    finally:
        document.close()


def _poppler_pdf_pages(path, settings, cancel):
    try:
        from pypdf import PdfReader
        document = PdfReader(str(path))
        count = len(document.pages)
    except Exception as exc:
        raise OCRError(f'Cannot open PDF (is it encrypted or damaged?): {exc}') from exc
    if count > settings.max_pages and not settings.last_page:
        raise OCRError(f'PDF has more than {settings.max_pages} pages. Select a page range.')
    for index, page in enumerate(document.pages):
        _check_cancel(cancel)
        number = index + 1
        if number < settings.first_page or (settings.last_page and number > settings.last_page):
            continue
        text = (page.extract_text() or '').replace('\r\n', '\n').strip()
        usable = len(re.findall(r'[^\W\d_]', text)) >= 25 and text.count('\ufffd') < max(1, len(text) // 100)
        if usable and not (settings.force_ocr or settings.region or settings.corners):
            yield number, text, None
            continue
        renderer = shutil.which('pdftoppm')
        if not renderer:
            raise OCRError('Scanned PDF OCR needs PDFium or the native Poppler pdftoppm tool.')
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        scale = min(settings.dpi / 72, (MAX_WORK_PIXELS / max(1, width * height)) ** .5)
        side = max(1, int(max(width, height) * scale))
        with tempfile.TemporaryDirectory(prefix='openmukti-pdf-') as temporary:
            output = Path(temporary) / 'page'
            code, _, err = _run([renderer, '-f', number, '-l', number, '-singlefile', '-scale-to', side,
                                 '-png', str(path), str(output)], timeout=settings.timeout, cancel=cancel)
            if code:
                raise OCRError('Poppler could not render PDF page: ' + err[:300])
            image = next(_safe_image_frames(output.with_suffix('.png')))[0]
        yield number, '', image


def import_ocr(path: str | Path, settings: OCRSettings | None = None, *, progress: Callable | None = None, cancel=None, _local=False):
    settings = settings or OCRSettings()
    settings.validate()
    path = Path(path).expanduser().resolve()
    # The Windows 3.15 main application delegates native imaging to its bundled
    # Python 3.12 worker, just as neural speech does for Piper.
    if not _local:
        from .ocr_sidecar import find_worker, import_with_worker
        if find_worker() is not None:
            return import_with_worker(path, settings, progress=progress, cancel=cancel)
    result, seen, chars = OCRResult(), 0, 0
    def add(image, source, number=None, embedded=None):
        nonlocal seen, chars
        _check_cancel(cancel)
        seen += 1
        number = number or seen
        if number < settings.first_page or (settings.last_page and number > settings.last_page):
            return
        if len(result.pages) >= settings.max_pages:
            raise OCRError(f'Book exceeds the {settings.max_pages}-page limit. Select a smaller range.')
        if progress:
            progress(number, settings.last_page, f'Reading {source}')
        if embedded is not None:
            result.pages.append(OCRPage(number, source, embedded, None, False, 'PDF text layer'))
            chars += len(embedded)
        else:
            spreads = [image]
            if settings.split_spreads and image.width > image.height * 1.25:
                middle = image.width // 2
                spreads = [image.crop((0, 0, middle, image.height)), image.crop((middle, 0, image.width, image.height))]
            for part, scan in enumerate(spreads):
                if len(result.pages) >= settings.max_pages:
                    raise OCRError('Split spreads exceed the OCR page limit.')
                text, confidence, mode = recognize_page(scan, settings, cancel=cancel)
                label = source + (f' ({"left" if part == 0 else "right"})' if len(spreads) > 1 else '')
                result.pages.append(OCRPage(number, label, text, confidence, True, mode))
                chars += len(text)
                if not text.strip():
                    result.warnings.append(f'No text recognized: {label}')
                elif confidence < 65:
                    result.warnings.append(f'Low OCR confidence ({confidence:.0f}%): {label}')
        if chars > MAX_TEXT_CHARS:
            raise OCRError('Recognized book exceeds the 20-million-character limit. Import it in parts.')
    try:
        if path.suffix.lower() == '.pdf':
            for number, text, image in _pdf_pages(path, settings, cancel):
                add(image, f'{path.name}, page {number}', number, text if image is None else None)
        elif path.suffix.lower() in {'.zip', '.cbz'}:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 30000 or sum(p.file_size for p in entries) > MAX_ARCHIVE_BYTES:
                    raise OCRError('Image archive exceeds the 2-GiB / 30,000-entry limit.')
                images = []
                for entry in entries:
                    name = entry.filename.replace('\\', '/')
                    parts = PurePosixPath(name).parts
                    if name.startswith('/') or '..' in parts or re.match(r'^[A-Za-z]:', name) or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                        raise OCRError('Unsafe image archive path or symbolic link.')
                    if entry.is_dir() or any(p.startswith('.') or p == '__MACOSX' for p in parts):
                        continue
                    if PurePosixPath(name).suffix.lower() in IMAGE_EXTENSIONS:
                        if entry.flag_bits & 1 or entry.file_size > MAX_PAGE_BYTES:
                            raise OCRError('An archived page is encrypted or exceeds 80 MiB.')
                        images.append(entry)
                if not images:
                    raise OCRError('The ZIP/CBZ contains no supported page images.')
                for entry in sorted(images, key=lambda p: natural_key(p.filename)):
                    _check_cancel(cancel)
                    with archive.open(entry) as stream:
                        raw = stream.read(MAX_PAGE_BYTES + 1)
                    if len(raw) > MAX_PAGE_BYTES:
                        raise OCRError('Archived image exceeds the page limit.')
                    for image, frame in _safe_image_frames(io.BytesIO(raw)):
                        add(image, entry.filename + (f' #{frame}' if frame > 1 else ''))
                    if settings.last_page and seen >= settings.last_page:
                        break
        else:
            files = sorted((p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.startswith('.')), key=natural_key) if path.is_dir() else [path]
            if not files:
                raise OCRError('The folder contains no supported page images.')
            for file in files:
                _check_cancel(cancel)
                if file.suffix.lower() not in IMAGE_EXTENSIONS:
                    raise OCRError(f'Unsupported scan format: {file.suffix}')
                if file.stat().st_size > MAX_PAGE_BYTES:
                    raise OCRError('Scan image exceeds 80 MiB.')
                for image, frame in _safe_image_frames(file):
                    add(image, file.name + (f' #{frame}' if frame > 1 else ''))
                if settings.last_page and seen >= settings.last_page:
                    break
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, DocumentError):
            raise
        raise OCRError(f'Cannot import scans: {exc}') from exc
    _check_cancel(cancel)
    if not result.pages:
        raise OCRError('No pages were selected. Check the page range.')
    if not result.text.strip():
        raise OCRError('No readable text was found. Try another preprocessing mode, language or segmentation setting.')
    return result


def create_searchable_pdf(source: str | Path, destination: str | Path,
                          settings: OCRSettings | None = None, *, progress=None, cancel=None) -> Path:
    """Create a PDF with Tesseract's invisible searchable text layer.

    Supports image files (including multi-page TIFF) and scanned PDFs. Existing
    PDFs are rasterized for this explicit export; use the original for archival
    fidelity. No network access, no downloaded OCR language data.
    """
    settings = settings or OCRSettings()
    settings.validate()
    original = Path(source).expanduser().resolve()
    dest = Path(destination).expanduser().resolve()
    binary = find_tesseract()
    if not binary:
        raise OCRError('Tesseract must be installed or bundled to create a searchable PDF')
    if original == dest or dest.suffix.lower() != '.pdf':
        raise OCRError('Choose a new PDF output path different from the original')
    if original.suffix.lower() not in IMAGE_EXTENSIONS | {'.pdf'}:
        raise OCRError('Searchable PDF creation supports a PDF or scanned page image')
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:
        raise OCRError('Install pypdf for multi-page searchable PDF assembly') from exc
    # OCR every page for text-position mapping, even if an embedded text layer
    # exists. This is a deliberate rasterized export, not lossless PDF editing.
    all_settings = OCRSettings(**{**asdict(settings), 'force_ocr': True})
    def pages():
        if original.suffix.lower() == '.pdf':
            for number, _, image in _pdf_pages(original, all_settings, cancel):
                if image is not None:
                    yield number, image
        else:
            for number, (image, _) in enumerate(_safe_image_frames(original), 1):
                if number >= settings.first_page and (not settings.last_page or number <= settings.last_page):
                    yield number, image
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openmukti-searchable-') as directory:
        root = Path(directory)
        writer = PdfWriter()
        total = 0
        for number, image in pages():
            _check_cancel(cancel)
            total += 1
            if total > settings.max_pages:
                raise OCRError('Searchable PDF exceeds page limit')
            if progress:
                progress(number, settings.last_page, f'Creating searchable PDF page {number}')
            scan = preprocess_image(select_page_area(image, settings), settings)
            scan_path = root / f'page-{number}.png'
            output_stem = root / f'page-{number}'
            scan.save(scan_path, dpi=(settings.dpi, settings.dpi))
            code, _, err = _run([binary, scan_path, output_stem, '-l', settings.language,
                                 '--oem', '1', '--psm', str(settings.psm), '--dpi', str(settings.dpi),
                                 *_tool_args(binary), 'pdf'], timeout=settings.timeout, cancel=cancel)
            if code:
                raise OCRError('Searchable PDF OCR failed: ' + err[:700])
            path = output_stem.with_suffix('.pdf')
            if not path.is_file():
                raise OCRError('Tesseract produced no searchable PDF page')
            # Writer.import_page validates and copies page objects before the
            # temporary per-page PDF is removed.
            page_reader = PdfReader(str(path))
            if len(page_reader.pages) != 1:
                raise OCRError('Tesseract produced an unexpected page count')
            writer.add_page(page_reader.pages[0])
        if total == 0:
            raise OCRError('No pages selected for searchable PDF export')
        fd, final_temp = tempfile.mkstemp(prefix='.openmukti-searchable-', suffix='.pdf', dir=dest.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                writer.write(out)
            os.replace(final_temp, dest)
        finally:
            Path(final_temp).unlink(missing_ok=True)
    return dest
