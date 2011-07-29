#!/usr/bin/env python

"""

nacl_try.py tests a NaCl change on the local machine, or on remote
machines by rsyncing the source tree to them.

Usage:
nacl_try.py "<scons args>" <dest machines...>

Examples:

nacl_try.py run_hello_world_test 32 64 mac winbox
- Runs a minimal test on x86-32 Linux, x86-64 Linux, Mac and Windows.

nacl_try.py 'run_hello_world_test --verbose' 32 64
- The first arg can contain multiple Scons arguments.

nacl_try.py '' 32 64
- This is how to invoke Scons with no arguments, so that it builds
everything.

To set up a machine for use with nacl_try.py, you must first check out
a copy of the NaCl source tree there.  For example:

$ ssh mymac
mac$ mkdir -p devel/nacl
mac$ cd devel/nacl
mac$ gclient config http://src.chromium.org/native_client/trunk/src/native_client
mac$ gclient sync

TODO: Add an option for running 'gclient sync'.
TODO: Add the ability to sync/test in parallel for different machines.

"""

import subprocess
import sys
import time


# This is a small helper for creating a Python object from a dict of
# closures (one closure per method).
class Obj(object):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def memo(func):
    done = [False]
    def wrapper():
        if not done[0]:
            func()
            done[0] = True
    return wrapper


def make_host(host, destdir, msvc=False, msvc64=False):
    # Memoize so that we only do the rsync once per destination
    # location, even if we test two configurations in that location
    # (e.g. x86-32 Mac and x86-64 Mac).
    @memo
    def sync():
        # Note that this never deletes files, so obsolete files will
        # get left behind in the destination directory.
        subprocess.check_call("git ls-files >filelist", shell=True)
        subprocess.check_call(
            "rsync -avz --files-from=filelist . %s:%s"
            % (host, destdir), shell=True)
    def run(cmd):
        if msvc:
            wrapper= "/usr/bin/python ~/setenv.py ~/env-vc"
        elif msvc64:
            wrapper= "/usr/bin/python ~/setenv.py ~/env-vc64"
        else:
            wrapper = ""
        subprocess.check_call(["ssh", "-t", host,
                               "cd %s && %s %s" % (destdir, wrapper, cmd)])
    return Obj(sync=sync, run=run)


def make_this_host():
    def run(cmd):
        subprocess.check_call(cmd, shell=True)
    return Obj(sync=lambda: None,
               run=run)


this_host = make_this_host()
macpro = make_host("hydric", "devel/nacl/native_client")
win32vm = make_host("win32vm", "devel/nacl/native_client", msvc=True)
win32vm64 = make_host("win32vm", "devel/nacl/native_client", msvc64=True)


dest_map = {}

def add_target(name, host, opts):
    dest_map[name] = (host, opts)

add_target("32", this_host,
           "--mode=dbg-linux,nacl platform=x86-32 -j2")
add_target("64", this_host,
           "--mode=dbg-linux,nacl platform=x86-64 -j2")
add_target("arm", this_host,
           "--mode=dbg-linux,nacl sdl=none platform=arm -j2")

add_target("mac", macpro, "--mode=dbg-mac,nacl -j6")
add_target("mac64", macpro, "--mode=dbg-mac,nacl -j6 platform=x86-64")
add_target("win", win32vm, "--mode=dbg-win,nacl")# -j3")
add_target("win64", win32vm64, "--mode=dbg-win,nacl platform=x86-64 sdl=none -j8")

add_target("winbox", make_host("winbox", "devel/nacl/native_client", msvc64=True),
           "--mode=dbg-win,nacl platform=x86-64")
add_target("winbox32", make_host("winbox", "devel/nacl/native_client", msvc=True),
           "--mode=dbg-win,nacl platform=x86-32")
add_target("hivewin32", make_host("hivewin32", "devel/nacl/native_client", msvc=True),
           "--mode=dbg-win,nacl")
add_target("hivexp32",
           make_host("hivexp32", "devel/nacl/native_client", msvc=True),
           "--mode=dbg-win,nacl")
add_target("benthic", make_host("benthic", "devel/nacl/native_client"),
           "--mode=dbg-linux,nacl")
add_target("xeric", make_host("xeric", "devel/nacl/native_client"),
           "--mode=dbg-host,nacl")


def main(args):
    target = args[0]
    dests = args[1:]
    if len(dests) == 0:
        print "No dests given"
        return 1

    opts_list = [(key, dest_map[key]) for key in dests]
    summary = []
    for name, (host, opts) in opts_list:
        host.sync()

        if target == 'sync':
            continue

        t0 = time.time()
        cmd = "./scons sysinfo=0 target_stats=0 %s %s" % (opts, target)
        #cmd = "cd .. && ./native_client/build/gyp_nacl native_client/build/all.gyp -f make && make -j4"
        host.run(cmd)
        t1 = time.time()

        took = t1 - t0
        summary.append("%s: OK, took %.1fs" % (name, took))
    print "\n" + "\n".join(summary)


if __name__ == "__main__":
    main(sys.argv[1:])
