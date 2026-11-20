#!/usr/local/python3.12.13/bin/python3
"""Drop-in bwrap front-end for the Ascend engine sandbox.

The host Ascend device nodes are 1000:1000 mode 660. The engine sandbox runs
its child inside a bwrap user namespace with all capabilities dropped, so the
child (kernel uid 0) cannot rely on CAP_DAC_OVERRIDE for device access, and
userns caps never apply to init-namespace-owned devtmpfs. Rebind tricks cannot
fix that, but a fresh character-device node with the same major/minor owned by
root mode 0600 on the container's writable /tmp can: the child is the owner,
so plain DAC grants read/write, and the driver still sees the real device.

This front-end rewrites every `--dev-bind SRC DST` whose SRC is a character
device to `--bind COPY DST` where COPY is such a node, then execs the real
bwrap. It changes no service code, no host state and no mount layout; the
scratch directory is removed when the child exits.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile

REAL_BWRAP = "/usr/bin/bwrap.real"


def main() -> int:
    args = sys.argv[1:]
    scratch = tempfile.mkdtemp(prefix="ascend-sbx-dev-")
    rewritten = []
    index = 0
    try:
        while index < len(args):
            arg = args[index]
            if arg == "--dev-bind" and index + 2 < len(args):
                source, destination = args[index + 1], args[index + 2]
                info = os.stat(source)
                if stat.S_ISCHR(info.st_mode):
                    copy = os.path.join(scratch, os.path.basename(source))
                    os.mknod(copy, 0o600 | stat.S_IFCHR, info.st_rdev)
                    rewritten += ["--dev-bind", copy, destination]
                    index += 3
                    continue
            rewritten.append(arg)
            index += 1
        return subprocess.call([REAL_BWRAP, *rewritten])
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
