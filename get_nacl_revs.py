#!/usr/bin/python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re
import subprocess

import nacl_deps_bump


# This script lists the Chromium revisions in which nacl_revision was
# changed in DEPS.


def GetCommandOutput(command):
  proc = subprocess.Popen(command, stdout=subprocess.PIPE)
  stdout = proc.communicate()[0]
  status = proc.wait()
  assert status == 0, (command, status)
  return stdout


# Returns (Chromium Git commit ID, nacl_revision) for each revision of
# Chromium.
def GetAllDepsRevs():
  proc = subprocess.Popen(['git', 'rev-list', 'origin/master', '--', 'DEPS'],
                          stdout=subprocess.PIPE)
  for line in proc.stdout:
    commit = line.rstrip('\n')
    deps = GetCommandOutput(['git', 'cat-file', 'blob', '%s:DEPS' % commit])
    match = nacl_deps_bump.MatchKey(deps, 'nacl_revision')
    assert match is not None
    nacl_rev = match.group(1)
    yield commit, nacl_rev


# Returns (Chromium Git commit ID, nacl_revision) for each revision of
# Chromium in which nacl_revision has been changed.
def GetDepsRevs():
  seq = GetAllDepsRevs()
  commit, nacl_rev = seq.next()
  while True:
    commit2, nacl_rev2 = seq.next()
    if nacl_rev != nacl_rev2:
      yield commit, nacl_rev
    commit = commit2
    nacl_rev = nacl_rev2


def GetSvnRevisionFromGitCommit(commit):
  data = GetCommandOutput(['git', 'cat-file', 'commit', commit])
  match = re.search('\ngit-svn-id: .*@(\d+).*\s*$', data, re.S)
  if match is None:
    raise AssertionError('No git-svn-id in %r' % data)
  return int(match.group(1))


# Get the SVN revision number of the last nacl_revision change.
def GetSvnLastDepsBump():
  commit, nacl_rev = GetDepsRevs().next()
  return GetSvnRevisionFromGitCommit(commit)


def Main():
  for commit, nacl_rev in GetDepsRevs():
    print GetSvnRevisionFromGitCommit(commit), nacl_rev


if __name__ == '__main__':
  Main()
