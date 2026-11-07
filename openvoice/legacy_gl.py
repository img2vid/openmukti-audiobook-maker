"""EGL / OpenGL ES 2.0 compositor for older or embedded graphics drivers.

The isolated process owns every driver handle. The application accepts a
hardware renderer only. Mesa software rendering is exposed to the self-test.
"""
from __future__ import annotations

import atexit
import ctypes as C
import ctypes.util
import json
import os
import struct
import subprocess
import sys
import threading
import time

I,U,P,F,S=C.c_int,C.c_uint,C.c_void_p,C.c_float,C.c_char_p
FIXED=0x3038
MAX_PIXELS=16_777_216
VERT=b'attribute vec2 pos; varying vec2 uv; void main(){uv=pos*0.5+0.5;gl_Position=vec4(pos,0.,1.);}'
FRAG=b'''
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
varying vec2 uv;uniform sampler2D back;uniform sampler2D front;
void main(){vec4 b=texture2D(back,uv),f=texture2D(front,uv);
float a=f.a+b.a*(1.-f.a);
gl_FragColor=f.a==0. ? b : vec4((f.rgb*f.a+b.rgb*b.a*(1.-f.a))/max(a,0.0001),a);}
'''


class EGLCompositor:
    def __init__(self,allow_software=False):
        lib=ctypes.util.find_library('EGL') or ('libEGL.dll' if os.name=='nt' else 'libEGL.so.1')
        self.lib=(C.WinDLL if os.name=='nt' else C.CDLL)(lib)
        self.fn=(C.WINFUNCTYPE if os.name=='nt' else C.CFUNCTYPE)
        self.egl('eglGetProcAddress',P,S)
        self.egl('eglGetDisplay',P,P)
        self.egl('eglInitialize',U,P,P,P)
        self.egl('eglBindAPI',U,U)
        self.egl('eglChooseConfig',U,P,P,P,I,P)
        self.egl('eglCreateContext',P,P,P,P,P)
        self.egl('eglMakeCurrent',U,P,P,P,P)
        self.egl('eglCreatePbufferSurface',P,P,P,P)
        self.egl('eglDestroySurface',U,P,P)
        self.egl('eglDestroyContext',U,P,P)
        self.egl('eglTerminate',U,P)
        self.display=self.eglGetDisplay(None)
        if not self.display or not self.eglInitialize(self.display,None,None):
            addr=self.eglGetProcAddress(b'eglGetPlatformDisplayEXT')
            if not addr:
                raise RuntimeError('No EGL display')
            self.display=self.fn(P,U,P,P)(addr)(0x31DD,None,None)
            if not self.display or not self.eglInitialize(self.display,None,None):
                raise RuntimeError('No usable EGL platform')
        if not self.eglBindAPI(0x30A0):
            raise RuntimeError('OpenGL ES is unavailable')
        attrs=[0x3033,1,0x3040,4,0x3024,8,0x3023,8,0x3022,8,0x3021,8,FIXED]
        self.config=P()
        count=I()
        if not self.eglChooseConfig(self.display,(I*len(attrs))(*attrs),C.byref(self.config),1,C.byref(count)) or not count.value:
            raise RuntimeError('No RGBA8 pbuffer config')
        self.ctx=self.eglCreateContext(self.display,self.config,None,(I*3)(0x3098,2,FIXED))
        if not self.ctx:
            raise RuntimeError('Cannot create an ES 2.0 context')
        self.surface=None
        self.size=None
        self.resize(1,1)
        self.gl('glGetString',S,U)
        self.name=(self.glGetString(0x1F01) or b'').decode('utf-8','replace')
        sw=any(x in self.name.lower() for x in ('llvmpipe','softpipe','swiftshader','software','basic render','lavapipe'))
        if not self.name or (sw and not allow_software):
            raise RuntimeError('Software rasterizer or missing GPU')
        self.software=sw
        specs=(('glCreateShader',U,U),('glShaderSource',None,U,I,P,P),('glCompileShader',None,U),('glGetShaderiv',None,U,U,P),
               ('glCreateProgram',U),('glAttachShader',None,U,U),('glLinkProgram',None,U),('glGetProgramiv',None,U,U,P),
               ('glUseProgram',None,U),('glGetAttribLocation',I,U,S),('glGetUniformLocation',I,U,S),('glUniform1i',None,I,I),
               ('glVertexAttribPointer',None,U,I,U,C.c_ubyte,I,P),('glEnableVertexAttribArray',None,U),
               ('glViewport',None,I,I,I,I),('glActiveTexture',None,U),('glGenTextures',None,I,P),
               ('glBindTexture',None,U,U),('glTexParameteri',None,U,U,I),('glTexImage2D',None,U,I,I,I,I,I,U,U,P),
               ('glDisable',None,U),('glDrawArrays',None,U,I,I),('glReadPixels',None,I,I,I,I,U,U,P),('glGetError',U))
        for name,restype,*types in specs:
            self.gl(name,restype,*types)
        self.program=self.glCreateProgram()
        for typ,source in ((0x8B31,VERT),(0x8B30,FRAG)):
            shader=self.glCreateShader(typ)
            src=S(source)
            self.glShaderSource(shader,1,C.byref(src),None)
            self.glCompileShader(shader)
            ok=I()
            self.glGetShaderiv(shader,0x8B81,C.byref(ok))
            if not ok.value:
                raise RuntimeError('Cannot compile the ES 2.0 compositor shader')
            self.glAttachShader(self.program,shader)
        self.glLinkProgram(self.program)
        ok=I()
        self.glGetProgramiv(self.program,0x8B82,C.byref(ok))
        if not ok.value:
            raise RuntimeError('Cannot link compositor shader')
        self.glUseProgram(self.program)
        self.glDisable(0x0BD0)
        self.textures=(U*2)()
        self.glGenTextures(2,self.textures)
        for i,label in enumerate((b'back',b'front')):
            self.glUniform1i(self.glGetUniformLocation(self.program,label),i)
        self.vertices=(F*8)(-1,-1,1,-1,-1,1,1,1)
        attr=self.glGetAttribLocation(self.program,b'pos')
        self.glVertexAttribPointer(attr,2,0x1406,0,0,self.vertices)
        self.glEnableVertexAttribArray(attr)

    def egl(self,name,result,*types):
        func=getattr(self.lib,name)
        func.restype=result
        func.argtypes=types
        setattr(self,name,func)

    def gl(self,name,result,*types):
        address=self.eglGetProcAddress(name.encode())
        if not address:
            raise RuntimeError('Graphics driver lacks '+name)
        setattr(self,name,self.fn(result,*types)(address))

    def resize(self,w,h):
        if self.size==(w,h):
            return
        surface=self.eglCreatePbufferSurface(self.display,self.config,(I*5)(0x3057,w,0x3056,h,FIXED))
        if not surface or not self.eglMakeCurrent(self.display,surface,surface,self.ctx):
            raise RuntimeError('Cannot activate render surface')
        if self.surface:
            self.eglDestroySurface(self.display,self.surface)
        self.surface=surface
        self.size=(w,h)

    def blend(self,w,h,bg,fg):
        if not 0<w*h<=MAX_PIXELS or len(bg)!=len(fg) or len(bg)!=4*w*h:
            raise ValueError('Invalid pixel buffers')
        self.resize(w,h)
        self.glViewport(0,0,w,h)
        for i,data in enumerate((bg,fg)):
            self.glActiveTexture(0x84C0+i)
            self.glBindTexture(0x0DE1,self.textures[i])
            for key,value in ((0x2801,0x2600),(0x2800,0x2600),(0x2802,0x812F),(0x2803,0x812F)):
                self.glTexParameteri(0x0DE1,key,value)
            self.glTexImage2D(0x0DE1,0,0x1908,w,h,0,0x1908,0x1401,C.cast(S(data),P))
        self.glDrawArrays(5,0,4)
        buf=C.create_string_buffer(4*w*h)
        self.glReadPixels(0,0,w,h,0x1908,0x1401,buf)
        if self.glGetError():
            raise RuntimeError('Compositor failed to render these inputs')
        return buf.raw

    def close(self):
        self.eglMakeCurrent(self.display,None,None,None)
        self.eglDestroySurface(self.display,self.surface)
        self.eglDestroyContext(self.display,self.ctx)
        self.eglTerminate(self.display)


def worker(probe_only=False,allow_software=False):
    try:
        driver=EGLCompositor(allow_software)
    except (OSError,RuntimeError) as exc:
        print(json.dumps({'available':False,'reason':str(exc)}),flush=True)
        return 0 if probe_only else 1
    try:
        known=driver.blend(1,1,bytes((240,0,0,255)),bytes((0,0,240,128)))
        if not (118<=known[0]<=121 and 119<=known[2]<=122 and known[3]==255):
            raise RuntimeError('Driver failed RGBA pixel test')
        print(json.dumps({'available':True,'renderer':driver.name,'software':driver.software,'pixel_test':list(known)}),flush=True)
        if probe_only:
            return 0
        while header:=sys.stdin.buffer.read(8):
            w,h=struct.unpack('<II',header)
            if not 0<w*h<=MAX_PIXELS:
                raise ValueError('Oversized pixel buffer')
            bg=sys.stdin.buffer.read(4*w*h)
            fg=sys.stdin.buffer.read(4*w*h)
            sys.stdout.buffer.write(driver.blend(w,h,bg,fg))
            sys.stdout.buffer.flush()
    finally:
        driver.close()
    return 0


class Renderer:
    def __init__(self):
        from .job_queue import cli_process
        cmd,env=cli_process()
        self.proc=subprocess.Popen([*cmd,'_gl-worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.stopped=threading.Event()
        self.deadline=time.monotonic()+8
        def monitor():
            while not self.stopped.wait(.5):
                if self.deadline and time.monotonic()>self.deadline:
                    if self.proc.poll() is None:
                        self.proc.kill()
                    break
        threading.Thread(target=monitor,daemon=True).start()
        try:
            response=json.loads(self.proc.stdout.readline())
            if not response.get('available'):
                raise RuntimeError('No hardware EGL renderer')
            self.name=response['renderer']
            self.deadline=0
        except BaseException:
            self.close()
            raise

    def close(self):
        self.stopped.set()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        for stream in (self.proc.stdin,self.proc.stdout):
            try:
                stream.close()
            except OSError:
                pass

    def blend(self,w,h,bg,fg):
        self.deadline=time.monotonic()+15
        self.proc.stdin.write(struct.pack('<II',w,h))
        self.proc.stdin.write(bg)
        self.proc.stdin.write(fg)
        self.proc.stdin.flush()
        data=self.proc.stdout.read(4*w*h)
        self.deadline=0
        if len(data)!=4*w*h:
            raise RuntimeError('Graphics worker disconnected')
        return data


_lock=threading.Lock()
_engine=None
_attempted=False


def may_work():
    return not _attempted or _engine is not None


def accelerated_blend(w,h,bg,fg):
    global _engine,_attempted
    if not 0<w*h<=MAX_PIXELS:
        return None
    with _lock:
        try:
            if not _attempted:
                _attempted=True
                _engine=Renderer()
                atexit.register(_engine.close)
            if _engine:
                return _engine.blend(w,h,bg,fg)
        except (OSError,ValueError,RuntimeError):
            if _engine:
                atexit.unregister(_engine.close)
                _engine.close()
                _engine=None
    return None
