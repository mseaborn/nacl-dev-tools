# Copyright (c) 2011 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import re
import subprocess
import sys
import time

import pysvn

# This script creates a code review for an update of Chromium's DEPS
# file to the latest revision of NaCl, and kicks off a try job.


def ReadFile(filename):
  fh = open(filename, "r")
  try:
    return fh.read()
  finally:
    fh.close()


def WriteFile(filename, data):
  fh = open(filename, "w")
  try:
    fh.write(data)
  finally:
    fh.close()


# The 'svn:' URL is faster than the 'http:' URL but only works if you
# have SVN committer credentials set up.
# nacl_svn = 'http://src.chromium.org/native_client/trunk/src/native_client'
nacl_svn = 'svn://svn.chromium.org/native_client/trunk/src/native_client'
# When querying for the latest revision, use the root URL.  Otherwise,
# if the most recent change touched a branch and not trunk, the query
# will return an empty list.
nacl_svn_root = 'svn://svn.chromium.org/native_client'


def MatchKey(data, key):
  return re.search('^\s*"%s": "(\S+)",\s*(#.*)?$' % key, data, re.M)


def GetDepsKey(data, key):
  match = MatchKey(data, key)
  return match.group(1)


def SetDepsKey(data, key, value):
  match = MatchKey(data, key)
  return ''.join([data[:match.start(1)],
                  value,
                  data[match.end(1):]])


def GetLatestRootRev():
  rev = pysvn.Revision(pysvn.opt_revision_kind.head)
  lst = pysvn.Client().log(nacl_svn_root, revision_start=rev, revision_end=rev,
                           discover_changed_paths=True)
  assert len(lst) == 1, lst
  return lst[0].revision.number


def GetNaClRev():
  now = time.time()
  rev_num = GetLatestRootRev()
  while True:
    rev = pysvn.Revision(pysvn.opt_revision_kind.number, rev_num)
    lst = pysvn.Client().log(nacl_svn, revision_start=rev, revision_end=rev)
    assert len(lst) in (0, 1), lst
    if len(lst) == 1:
      age_mins = (now - lst[0].date) / 60
      print 'r%i committed %.1f minutes ago' % (
          lst[0].revision.number, age_mins)
      if age_mins >= 10:
        return lst[0].revision.number
    rev_num -= 1


def GetLog(rev1, rev2):
  items = pysvn.Client().log(
      nacl_svn,
      revision_start=pysvn.Revision(pysvn.opt_revision_kind.number, rev1 + 1),
      revision_end=pysvn.Revision(pysvn.opt_revision_kind.number, rev2))
  got = []
  for item in items:
    line1 = item.message.split('\n')[0]
    got.append('r%i: %s\n' % (item.revision.number, line1))
  return ''.join(got)


def Main():
  # TODO: Check that there are no uncommitted changes first.
  subprocess.check_call(['git', 'fetch'])
  subprocess.check_call(['git', 'checkout', 'origin/trunk'])

  # TODO: The IRT is not always uploaded for the latest rev, so maybe
  # we should skip very new revisions.
  svn_rev = GetNaClRev()

  deps_data = ReadFile('DEPS')
  old_rev = GetDepsKey(deps_data, 'nacl_revision')
  deps_data = SetDepsKey(deps_data, 'nacl_revision', str(svn_rev))
  old_rev = int(old_rev)

  msg = 'NaCl: Update revision in DEPS, r%i -> r%i' % (old_rev, svn_rev)
  msg += '\n\nThis pulls in the following Native Client changes:\n\n'
  msg += GetLog(old_rev, svn_rev)
  msg += '\nBUG=none\nTEST=trybots\n'
  print msg

  # We don't just run this because it only prints the new DEPS lines.
  #subprocess.check_call([sys.executable, 'src/build/download_nacl_irt.py'],
  #                      cwd='..')

  # TODO: This duplicates a chunk of stuff from download_nacl_irt.py.
  sys.path.insert(0, 'build')
  import download_nacl_irt
  arches = ('x86_32', 'x86_64')
  nacl_dir = 'native_client'
  base_url = ('http://commondatastorage.googleapis.com/'
              'nativeclient-archive2/irt')
  for arch in arches:
    url = '%s/r%s/irt_%s.nexe' % (base_url, svn_rev, arch)
    dest_dir = os.path.join(nacl_dir, 'irt_binaries')
    if not os.path.exists(dest_dir):
      os.makedirs(dest_dir)
    dest_path = os.path.join(dest_dir, 'nacl_irt_%s.nexe' % arch)
    download_nacl_irt.DownloadFileWithRetry(dest_path, url)
    downloaded_hash = download_nacl_irt.HashFile(dest_path)
    key = 'nacl_irt_hash_%s' % arch
    deps_data = SetDepsKey(deps_data, key, downloaded_hash)

  # Copy revision numbers across from native_client/DEPS.
  # We do this because 'From()' is not supported in Chrome's DEPS.
  proc = subprocess.Popen(['svn', 'cat', '%s/DEPS@%s' % (nacl_svn, svn_rev)],
                          stdout=subprocess.PIPE)
  nacl_deps = proc.communicate()[0]
  assert proc.wait() == 0, proc.wait()
  deps_data = SetDepsKey(deps_data, 'nacl_chrome_ppapi_revision',
                         GetDepsKey(nacl_deps, 'chrome_ppapi_rev'))
  deps_data = SetDepsKey(deps_data, 'nacl_tools_revision',
                         GetDepsKey(nacl_deps, 'tools_rev'))

  WriteFile('DEPS', deps_data)

  subprocess.check_call(['git', 'checkout', '-b', 'auto-deps'])
  subprocess.check_call(['git', 'commit', '-a', '-m', msg])

  # TODO: Remove hard-coded path.
  # TODO: This can ask for credentials when the cached credentials
  # expire, so could fail when automated.  Can we fix that?
  subprocess.check_call(['/home/mseaborn/devel/depot_tools_latest/git-cl',
                         'upload', '-m', msg])
  subprocess.check_call([
      '/home/mseaborn/devel/depot_tools_latest/git-try',
      '--email', 'mseaborn@chromium.org',
      '-rHEAD',
      # TODO: Omit -t to be thorough.
      '-t', 'nacl_integration',
      # This CC does not happen by default for DEPS.
      '--cc', 'native-client-reviews@googlegroups.com',
      ])


if __name__ == '__main__':
  Main()
