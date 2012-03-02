#!/usr/bin/env python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import optparse
import subprocess
import sys
import time

# This dependency can be installed with:
# apt-get install python-svn
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
  match = re.search('^\s*"%s":\s*"(\S+)",\s*(#.*)?$' % key, data, re.M)
  if match is None:
    raise Exception('Key %r not found' % key)
  return match


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
      return lst[0].revision.number
    rev_num -= 1


def GetLog(rev1, rev2):
  items = pysvn.Client().log(
      nacl_svn,
      revision_start=pysvn.Revision(pysvn.opt_revision_kind.number, rev1 + 1),
      revision_end=pysvn.Revision(pysvn.opt_revision_kind.number, rev2))
  got = []
  authors = []
  for item in items:
    line1 = item.message.split('\n')[0]
    author = item.author.split('@', 1)[0]
    if line1 == 'Update .DEPS.git' and author == 'chrome-admin':
      # Skip these automated commits.
      continue
    authors.append(item.author)
    got.append('r%i: (%s) %s\n' % (item.revision.number, author, line1))
  return ''.join(got), authors


def Main():
  parser = optparse.OptionParser()
  parser.add_option('-t', '--toolchain', action='store_true', default=False,
                    help='Update NaCl toolchain revisions too')
  parser.add_option('-n', '--no-commit', action='store_true', default=False,
                    help='Do not run "git commit" (implies --no-upload)')
  parser.add_option('-u', '--no-upload', action='store_true', default=False,
                    help='Do not run "git cl upload" (implies --no-try)')
  parser.add_option('-T', '--no-try', action='store_true', default=False,
                    help='Do not start a trybot run')
  options, args = parser.parse_args()
  if len(args) != 0:
    parser.error('Got unexpected arguments')

  # Check for uncommitted changes.  Note that this can still lose
  # changes that have been committed to a detached-HEAD branch, but
  # those should be retrievable via the reflog.  This can also lose
  # changes that have been staged to the index but then undone in the
  # working files.
  proc = subprocess.Popen(['git', 'diff', '--name-only', 'HEAD'],
                          stdout=subprocess.PIPE)
  changes = proc.communicate()[0]
  assert proc.wait() == 0, proc.wait()
  if len(changes) != 0:
    raise AssertionError('You have uncommitted changes:\n%s' % changes)

  svn_rev = GetNaClRev()

  subprocess.check_call(['git', 'fetch'])
  branch_name = 'nacl-deps-r%s' % svn_rev
  subprocess.check_call(['git', 'checkout', '-b', branch_name,
                         'origin/master'])

  deps_data = ReadFile('DEPS')
  old_rev = GetDepsKey(deps_data, 'nacl_revision')
  deps_data = SetDepsKey(deps_data, 'nacl_revision', str(svn_rev))
  old_rev = int(old_rev)

  msg_logs, authors = GetLog(old_rev, svn_rev)
  msg = 'NaCl: Update revision in DEPS, r%i -> r%i' % (old_rev, svn_rev)
  msg += '\n\nThis pulls in the following Native Client changes:\n\n'
  msg += msg_logs
  msg += '\nBUG=none\nTEST=nacl_integration\n'
  print msg
  cc_list = ', '.join(['native-client-reviews@googlegroups.com'] +
                      sorted(set(authors)))
  print 'CC:', cc_list

  # Copy revision numbers across from native_client/DEPS.
  # We do this because 'From()' is not supported in Chrome's DEPS.
  proc = subprocess.Popen(['svn', 'cat', '%s/DEPS@%s' % (nacl_svn, svn_rev)],
                          stdout=subprocess.PIPE)
  nacl_deps = proc.communicate()[0]
  assert proc.wait() == 0, proc.wait()
  deps_data = SetDepsKey(deps_data, 'nacl_tools_revision',
                         GetDepsKey(nacl_deps, 'tools_rev'))

  if options.toolchain:
    x86_toolchain_rev = GetDepsKey(nacl_deps, 'x86_toolchain_version')
    deps_data = SetDepsKey(deps_data, 'nacl_toolchain_revision',
                           x86_toolchain_rev)
    pnacl_toolchain_rev = GetDepsKey(nacl_deps, 'pnacl_toolchain_version')
    deps_data = SetDepsKey(deps_data, 'pnacl_toolchain_revision',
                           pnacl_toolchain_rev)

    sys.path.insert(0, 'native_client/build')
    import download_toolchains
    import toolchainbinaries

    # Mock up the optparse options object GetUpdatedDEPS expects.
    class DownloadOptions(object):
      nacl_newlib_only = False
      no_pnacl = False
      no_arm_trusted = True
      base_url = toolchainbinaries.BASE_DOWNLOAD_URL
      x86_version = x86_toolchain_rev
      pnacl_version = pnacl_toolchain_rev

    toolchain_deps = download_toolchains.GetUpdatedDEPS(DownloadOptions())
    for key, value in toolchain_deps.iteritems():
      deps_data = SetDepsKey(deps_data, key, value)

  WriteFile('DEPS', deps_data)

  if options.no_commit:
    return
  subprocess.check_call(['git', 'commit', '-a', '-m', msg])

  if options.no_upload:
    return
  # TODO: This can ask for credentials when the cached credentials
  # expire, so could fail when automated.  Can we fix that?
  subprocess.check_call(['git', 'cl',
                         'upload',
                         '-m', msg,
                         # This CC does not happen by default for DEPS.
                         '--cc', cc_list,
                         ])
  if options.no_try:
    return
  subprocess.check_call(['git', 'try',
                         '-b', 'linux_rel,mac_rel,win_rel,linux_chromeos',
                         ])


if __name__ == '__main__':
  Main()
