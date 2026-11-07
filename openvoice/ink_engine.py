"""Offline stroke-painting and pressure-aware pen/brush simulation.

Final artwork consists entirely of procedural pen/brush strokes, NOT printed
raster glyphs. Preferred input is a human-authored trajectory library, which
contains genuine hand-drawn stroke order for any Unicode grapheme cluster.
When no trajectory exists, an automatic medial-axis tracer uses a fully shaped
font raster *as a layout guide only*. Such a reconstruction cannot guarantee
culturally correct strokes or authentic handwriting; strict mode rejects gaps.
No GPU, OpenCV, NumPy or online service is needed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from .stroke_library import StrokeLibrary


@dataclass(frozen=True)
class PenStroke:
    points: tuple[tuple[float, float], ...]
    lengths: tuple[float, ...]
    length: float
    pressures: tuple[float, ...] = ()


@dataclass
class InkStep:
    start: float
    end: float
    left: int
    top: int
    source: Image.Image
    strokes: tuple[PenStroke, ...]
    total_length: float
    authored: bool = False


def _skeletonize(alpha: Image.Image) -> Image.Image:
    """Pillow-only morphological skeleton; work on small cropped text cells."""
    pixels = alpha.point(lambda v: 255 if v >= 66 else 0)
    result = Image.new('L', pixels.size, 0)
    erode = ImageFilter.MinFilter(3)
    dilate = ImageFilter.MaxFilter(3)
    for _ in range(48):
        if pixels.getbbox() is None:
            break
        shrunk = pixels.filter(erode)
        opened = shrunk.filter(dilate)
        result = ImageChops.lighter(result, ImageChops.subtract(pixels, opened))
        pixels = shrunk
    return result


def _trace_paths(mask: Image.Image, direction: str) -> tuple[PenStroke, ...]:
    """Walk skeleton graph as continuous pen gestures; avoid contour retracing."""
    width, height = mask.size
    raw = mask.tobytes()
    remaining = {(i % width, i // width) for i, c in enumerate(raw) if c > 30}
    if not remaining:
        return ()
    # 8-connectivity captures diagonal pen gestures and curved terminals.
    neighbors = ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1))
    all_points = remaining.copy()
    degrees = {}
    for x, y in all_points:
        degrees[x,y] = sum((x+dx,y+dy) in all_points for dx,dy in neighbors)

    def key(point):
        x,y=point
        return ((-x if direction=='rtl' else x), y)

    endpoints = sorted((p for p in all_points if degrees[p] <= 1), key=key)
    # Endpoints first; then remaining isolated loops/branches.
    paths=[]
    while remaining:
        while endpoints and endpoints[0] not in remaining:
            endpoints.pop(0)
        start = endpoints.pop(0) if endpoints else min(remaining, key=key)
        current=start
        previous=None
        points=[]
        while current in remaining:
            remaining.remove(current)
            points.append(current)
            x,y=current
            choices=[(x+dx,y+dy) for dx,dy in neighbors if (x+dx,y+dy) in remaining]
            if not choices:
                break
            if previous is None:
                # Prefer connected filaments, not a jump to a different glyph.
                choices.sort(key=lambda p:(degrees[p]>2, key(p)))
            else:
                vx,vy=x-previous[0],y-previous[1]
                choices.sort(key=lambda p:(-(p[0]-x)*vx-(p[1]-y)*vy,
                                           degrees[p]>2,key(p)))
            previous,current=current,choices[0]
        if points:
            lengths=[0.0]
            for a,b in zip(points,points[1:]):
                lengths.append(lengths[-1]+math.hypot(a[0]-b[0],a[1]-b[1]))
            # Give single-point marks measurable duration to keep diacritics.
            distance=max(1.0,lengths[-1])
            paths.append(PenStroke(tuple(points),tuple(lengths),distance))
    # Reorder whole gestures in the logical writing direction. Stable within a
    # line, even if the skeletonizer returned the components in random order.
    paths.sort(key=lambda p:key(p.points[0]))
    return tuple(paths)


def script_gestures(paths, cluster, width, height):
    """Order reconstructed gestures using script geometry. Authored trajectories bypass this."""
    if len(paths)<2 or not cluster:
        return paths
    import unicodedata
    names=' '.join(unicodedata.name(ch,'') for ch in cluster)
    def shape(p):
        xs,ys=zip(*p.points)
        return min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)
    if 'ARABIC' in names or 'HEBREW' in names:
        # Write the connected body from the right; add detached dots and points afterwards.
        return tuple(sorted(paths,key=lambda p:(p.length<height*.24,-shape(p)[0],shape(p)[1])))
    if 'BENGALI' in names or 'DEVANAGARI' in names or 'GURMUKHI' in names:
        def indic(p):
            x,y,w,h=shape(p)
            headline=w>width*.46 and h<height*.2 and y<height*.45
            return (headline,x,y)
        return tuple(sorted(paths,key=indic))
    if any(s in names for s in ('CJK','HIRAGANA','KATAKANA','HANGUL')):
        # Canonical authored order takes precedence when supplied. This geometric
        # model favors upper-left starts and horizontal strokes at intersections.
        return tuple(sorted(paths,key=lambda p:(round(shape(p)[1]/max(1,height*.2)),shape(p)[0],shape(p)[3]>shape(p)[2])))
    return paths


def prepare_step(ink: Image.Image, x0: float, x1: float, y: int, height: int,
                 start: float, end: float, direction: str, *, trace: bool = True,
                 trajectories=None, strict: bool = False, cluster: str = "") -> InkStep | None:
    """Precompute a trace for one timestamped grapheme cluster in the shaped line."""
    # Coordinate conversion: width offsets in text logical order; right-to-left
    # boundaries must be mirrored across the entire measured line by the caller.
    left=max(0,min(ink.width,math.floor(min(x0,x1))))
    right=max(0,min(ink.width,math.ceil(max(x0,x1))))
    top=max(0,y-2)
    bottom=min(ink.height,y+height+2)
    if right<=left or bottom<=top:
        return None
    source=ink.crop((left,top,right,bottom))
    alpha=source.getchannel('A')
    bbox=alpha.getbbox()
    if not bbox and not trajectories:
        return None
    # Trim empty edges for smaller pen masks and faster per-frame rendering.
    # Retain 1px halo so nib tips on the crop edge are not lost.
    if bbox:
        l=max(0,bbox[0]-1);t=max(0,bbox[1]-1)
        r=min(source.width,bbox[2]+1);b=min(source.height,bbox[3]+1)
    else:
        l=t=0;r=source.width;b=source.height
    source=source.crop((l,t,r,b));left+=l;top+=t
    if trajectories:
        # The path source is the person's drawing, with preserved pen lifts,
        # ordering, variation and tablet pressure. Glyph pixels are discarded.
        paths=[]
        for trajectory in trajectories:
            pts=[(px*max(1,source.width-1),py*max(1,source.height-1)) for px,py,_ in trajectory.points]
            pressures=[pressure for _,_,pressure in trajectory.points]
            lens=[0.0]
            for a,b in zip(pts,pts[1:]):
                lens.append(lens[-1]+math.dist(a,b))
            paths.append(PenStroke(tuple(pts),tuple(lens),max(1.0,lens[-1]),tuple(pressures)))
        paths=tuple(paths)
    elif strict and trace:
        raise ValueError('Strict hand-drawn mode requires a stroke template for every grapheme')
    else:
        paths=_trace_paths(_skeletonize(source.getchannel('A')),direction) if trace else ()
        paths=script_gestures(paths,cluster,source.width,source.height)
    if trace and not paths:
        # Even a one-pixel accent must be drawn, not silently discarded.
        paths=(PenStroke(((source.width//2,source.height//2),),(0.0,),1.0),)
    return InkStep(start,end,left,top,source,paths,sum(p.length for p in paths),bool(trajectories))


def prepare_line(ink: Image.Image, x: int, y: int, width: int, height: int,
                 direction: str, steps: list[tuple[float,float,float,float]],
                 *, trace: bool = True, clusters: list[str] | None = None,
                 library: StrokeLibrary | None = None, strict: bool = False) -> list[InkStep]:
    """Split a fully shaped Unicode line on grapheme/timestamp boundaries."""
    result=[]
    if not steps:return result
    # Clamp the cumulative advance sequence into contiguous, exhaustive
    # strips. OpenType can have non-monotonic widths as contextual joins form.
    # The last strip must reach the right edge, including any trailing marks.
    unit_width=max(0.001,max(value for _,_,a,b in steps for value in (a,b)))
    boundaries=[0.0]
    for _,_,_,b in steps[:-1]:
        boundaries.append(max(boundaries[-1], min(1.0, b/unit_width)))
    boundaries.append(1.0)
    # A trajectory library may define complete words/conjuncts, not only
    # individual graphemes. Prefer the longest exact match; this preserves
    # connections and pen lifts authored across an entire handwritten word.
    i=0
    while i<len(steps):
        stop=i+1
        authored=None
        if library is not None and clusters:
            for j in range(min(len(steps),i+32),i,-1):
                candidate=''.join(clusters[i:j])
                if len(candidate)>64:continue
                paths=library.lookup(candidate)
                if paths:
                    stop=j
                    authored=paths
                    break
        start=steps[i][0]
        end=steps[stop-1][1]
        a,b=boundaries[i],boundaries[stop]
        if direction=='rtl':
            left=x+width*(1.0-b)
            right=x+width*(1.0-a)
        else:
            left=x+width*a
            right=x+width*b
        cluster=''.join(clusters[i:stop]) if clusters else ''
        if trace and not strict and not authored:
            from .native_strokes import trajectories as built_in_trajectories
            authored=built_in_trajectories(cluster)
        if strict and trace and not authored:
            raise ValueError(f'Missing hand-drawn stroke template for {cluster!r}. '
                             'Open Stroke Studio and draw this character, or disable strict mode.')
        step=prepare_step(ink,left,right,y,height,start,end,direction,trace=trace,
                          trajectories=authored,strict=strict,cluster=cluster)
        if step is not None:
            result.append(step)
        i=stop
    return result


def _sample_path(path: PenStroke, budget: float, spacing: float = .80):
    """Resample authored tablet or traced trajectories at uniform arc distance.

    Human pressure points are interpolated between segments; a deterministic
    pen-speed modulation supplies variation where tablet pressure is absent.
    """
    if not path.points or budget <= 0:
        return []
    if len(path.points)==1:
        x,y=path.points[0]
        return [(x,y,path.pressures[0] if path.pressures else .85)]
    limit=min(path.length,budget)
    samples=[]
    d=0.0
    j=1
    while d <= limit+1e-5:
        while j < len(path.lengths)-1 and path.lengths[j] < d:
            j+=1
        start=path.lengths[j-1];end=path.lengths[j]
        frac=min(1.0,max(0.0,(d-start)/max(1e-6,end-start)))
        x=path.points[j-1][0]*(1-frac)+path.points[j][0]*frac
        y=path.points[j-1][1]*(1-frac)+path.points[j][1]*frac
        if path.pressures:
            pressure=path.pressures[j-1]*(1-frac)+path.pressures[j]*frac
        else:
            # Natural pressure rise/fall, altered at turn and pen lift.
            phase=d/max(1.0,path.length)
            pressure=(.60+.32*min(1.,phase*10, (1-phase)*12))
        samples.append((x,y,pressure))
        d+=spacing
    if limit and samples and abs(d-spacing-limit)>.2:
        samples.append((*path.points[-1],path.pressures[-1] if path.pressures else .65) if limit>=path.length else samples[-1])
    return samples


def _paint(step: InkStep, fraction: float, *, calligraphy: bool, font_size: int,
           nib_angle: int, pen_width: int, pigment: tuple[int,int,int] | None = None,
           paper_grain: int = 14, brush_dryness: int = 12, pressure_scale: float = 1.0,
           pen_tool: str = 'auto'):
    """Draw pigmented pen/brush footprints, never copy printed glyph pixels.

    Edge feathering, speed-dependent pressure, nib rotation, ink pool at slow
    tips, and deterministic microtexture are computed in local coordinates.
    """
    import math
    w,h=step.source.size
    scale=2  # Antialias all nib silhouettes by painting above output resolution.
    mask=Image.new('L',(w*scale,h*scale),0)
    drawer=ImageDraw.Draw(mask)
    budget=max(0.0,min(1.0,fraction))*step.total_length
    cursor=None
    tool=pen_tool if pen_tool != 'auto' else ('broad-nib' if calligraphy else 'ballpoint')
    base=(pen_width/2.0 if pen_width else font_size*(.046 if tool not in ('broad-nib','brush') else .039))
    if tool=='pencil': base*=.72
    if tool=='fountain': base*=.84
    if tool=='brush': base*=1.35
    base=max(0.8,base)
    phi=math.radians(nib_angle)
    vx,vy=math.cos(phi),math.sin(phi)
    counter=0
    for stroke_idx,path in enumerate(step.strokes):
        if budget <= 0: break
        samples=_sample_path(path,min(budget,path.length),.80)
        for i,(x,y,pressure) in enumerate(samples):
            pressure=max(.10,min(1.0,pressure*pressure_scale))
            # Small deterministic variations in nib orientation/pressure.
            jitter=1+.045*math.sin(i*.57+stroke_idx*9.1)
            radius=max(.65,base*pressure*jitter)
            if tool in ('broad-nib','brush','fountain'):
                # An elliptical broad nib, flat edge, rotating slightly with
                # hand motion. No glyph-shaped masks are used.
                tangent=0.0
                if i>0:
                    tangent=math.atan2(y-samples[i-1][1],x-samples[i-1][0])
                curvature=.13*math.sin(tangent-phi)
                cx=math.cos(phi+curvature);cy=math.sin(phi+curvature)
                span=max(.75,radius*(1.40 if tool=='broad-nib' else (1.6 if tool=='brush' else 1.02)))
                minor=max(.50,radius*(.24 if tool=='broad-nib' else (.40 if tool=='brush' else .62)))
                corners=[(x+cx*span-cy*minor,y+cy*span+cx*minor),
                         (x-cx*span-cy*minor,y-cy*span+cx*minor),
                         (x-cx*span+cy*minor,y-cy*span-cx*minor),
                         (x+cx*span+cy*minor,y+cy*span-cx*minor)]
                drawer.polygon([(a*scale,b*scale) for a,b in corners],fill=255)
                # Brush fibers produce a natural feathered impression.
                if brush_dryness<65:
                    drawer.ellipse(((x-minor)*scale,(y-minor)*scale,(x+minor)*scale,(y+minor)*scale),fill=250)
            else:
                drawer.ellipse(((x-radius)*scale,(y-radius)*scale,(x+radius)*scale,(y+radius)*scale),fill=255)
            cursor=(round(x),round(y))
            counter+=1
        budget-=path.length
    if cursor and fraction > .01:
        # Ink pools subtly where the nib slows down / stops.
        px,py=cursor
        r=max(.7,base*.4)
        drawer.ellipse(((px-r)*scale,(py-r)*scale,(px+r)*scale,(py+r)*scale),fill=255)
    mask=mask.resize((w,h),Image.Resampling.LANCZOS)
    if pigment is None:
        return mask,cursor
    # Apply translucent edge bleed: a subtle watercolor feather rather than
    # a shadow around the printed typeface.
    if tool in ('brush','broad-nib') and max(w,h)>3:
        blur=mask.filter(ImageFilter.GaussianBlur(.65))
        mask=ImageChops.lighter(mask,blur.point(lambda v:int(v*.22)))
    if paper_grain or brush_dryness:
        raw=bytearray(mask.tobytes())
        for idx,v in enumerate(raw):
            if not v: continue
            x=idx%w;y=idx//w
            # Integer hash gives repeatable paper texture across video frames.
            seed=(x*73856093 ^ y*19349663 ^ 0x4f1bbcdc)&0xffffffff
            seed^=seed>>13;seed=(seed*1274126177)&0xffffffff
            noise=(seed&255)/255
            fade=paper_grain*noise*.45
            if tool in ('brush','broad-nib','pencil') and noise < .12:
                fade+=brush_dryness*.8*(.12-noise)/.12
            elif not calligraphy:
                fade+=brush_dryness*noise*.10
            raw[idx]=max(0,min(255,round(v-fade)))
        mask=Image.frombytes('L',(w,h),bytes(raw))
    out=Image.new('RGBA',(w,h),(*pigment,0));out.putalpha(mask)
    return out,cursor


def stylize_step(step: InkStep, *, calligraphy: bool, font_size: int,
                 color: tuple[int,int,int], nib_angle: int = -32,
                 pen_width: int = 0, paper_grain: int = 14,
                 brush_dryness: int = 12, pen_tool: str = 'auto') -> None:
    """Bake *actual drawn strokes* as final art; discard all font pixels."""
    # Allow nib to extend outside skeleton source area without clipping.
    pad=max(3,round((pen_width if pen_width else font_size*.16)*1.6))
    w,h=step.source.size
    step.source=Image.new('RGBA',(w+2*pad,h+2*pad),(0,0,0,0))
    step.left-=pad;step.top-=pad
    step.strokes=tuple(PenStroke(tuple((x+pad,y+pad) for x,y in p.points),
                                p.lengths,p.length,p.pressures) for p in step.strokes)
    drawn,_=_paint(step,1.,calligraphy=calligraphy,font_size=font_size,
                   nib_angle=nib_angle,pen_width=pen_width,pigment=color,
                   paper_grain=paper_grain,brush_dryness=brush_dryness,pen_tool=pen_tool)
    step.source=drawn


def draw_step(step: InkStep, fraction: float, *, calligraphy: bool, font_size: int,
              nib_angle: int = -32, pen_width: int = 0, paper_grain: int = 14,
              brush_dryness: int = 12,pen_tool: str = 'auto'):
    """Return authentic partial pen painting and current nib location."""
    if fraction >= .99999: return step.source,None
    if fraction<=0:return None,None
    color=step.source.getpixel((0,0))[:3]
    # Transparent corner still contains correct pigment RGB after putalpha.
    result,cursor=_paint(step,fraction,calligraphy=calligraphy,font_size=font_size,
                         nib_angle=nib_angle,pen_width=pen_width,pigment=color,
                         paper_grain=paper_grain,brush_dryness=brush_dryness,pen_tool=pen_tool)
    if cursor is not None: cursor=(step.left+cursor[0],step.top+cursor[1])
    return result,cursor
