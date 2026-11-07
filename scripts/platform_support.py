"""Host and binary identities used to prevent incorrectly labelled releases."""
from __future__ import annotations
import platform
import struct
import sys
import sysconfig
from pathlib import Path


def architecture(value=None):
    value = (value or platform.machine()).lower().replace('-', '_')
    if value == 'i86pc':
        return 'x86_64' if struct.calcsize('P') == 8 else 'i686'
    aliases = {'amd64':'x86_64', 'x64':'x86_64', 'arm64':'aarch64', 'armv8l':'armv7',
               'i386':'i686', 'i486':'i686', 'i586':'i686', 'x86':'i686',
               'armv7l':'armv7', 'armhf':'armv7', 'ppc64el':'ppc64le',
               'powerpc64le':'ppc64le', 'powerpc64':'ppc64', 'sun4v':'sparc64', 'sun4u':'sparc64'}
    return aliases.get(value, value)


def system():
    name = platform.system().lower()
    if name == 'darwin': return 'macos'
    if name == 'sunos':
        return 'illumos' if any(x in platform.version().lower() for x in ('illumos','omnios','openindiana')) else 'solaris'
    if name.startswith('dragonfly'): return 'dragonfly'
    return name


def windows_arch():
    value = sysconfig.get_platform().lower()
    return 'aarch64' if 'arm64' in value else 'x86_64' if 'amd64' in value else 'i686'


def pe_arch(path):
    with Path(path).open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ': raise ValueError(f'Invalid PE header: {path}')
        offset = struct.unpack_from('<I', dos, 60)[0]
        if offset < 64 or offset > Path(path).stat().st_size - 6: raise ValueError(f'Invalid PE offset: {path}')
        stream.seek(offset)
        signature = stream.read(6)
    if signature[:4] != b'PE\0\0': raise ValueError(f'Invalid PE signature: {path}')
    machine = struct.unpack('<H', signature[4:])[0]
    if machine not in {0x14c, 0x8664, 0xaa64, 0x1c4}: raise ValueError(f'Unknown PE machine {machine:#x}')
    return {0x14c:'i686', 0x8664:'x86_64', 0xaa64:'aarch64', 0x1c4:'armv7'}[machine]


def elf_arch(path):
    with Path(path).open('rb') as stream: data = stream.read(20)
    if len(data) < 20 or data[:4] != b'\x7fELF': raise ValueError(f'Invalid ELF header: {path}')
    order = '<' if data[5] == 1 else '>'
    machine = struct.unpack(order+'H', data[18:20])[0]
    names = {3:'i686', 62:'x86_64', 40:'armv7', 183:'aarch64', 21:'ppc64le' if data[5] == 1 else 'ppc64',
             22:'s390x', 243:'riscv64', 258:'loongarch64', 43:'sparc64'}
    if machine not in names: raise ValueError(f'Unknown ELF machine {machine}')
    return names[machine]


def macho_arch(path):
    with Path(path).open('rb') as stream: header = stream.read(8)
    orders = {b'\xcf\xfa\xed\xfe':'<', b'\xfe\xed\xfa\xcf':'>',
              b'\xce\xfa\xed\xfe':'<', b'\xfe\xed\xfa\xce':'>'}
    if len(header) < 8 or header[:4] not in orders:
        raise ValueError(f'Expected a native thin Mach-O executable: {path}')
    machine = struct.unpack(orders[header[:4]] + 'I', header[4:8])[0]
    if machine not in {0x1000007, 0x100000c}:
        raise ValueError(f'Unsupported Mach-O CPU {machine:#x}')
    return {0x1000007:'x86_64', 0x100000c:'aarch64'}[machine]
