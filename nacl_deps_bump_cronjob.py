#!/usr/bin/env python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
This tool is a wrapper around nacl_deps_bump.py that is intended to be
run from a cron job.

This tool kicks off try jobs for updating nacl_revision in Chromium's
DEPS file.  To reduce load on the try servers, it kicks off a new try
job when a sufficient number of new NaCl revisions have appeared, or a
sufficient time has elapsed, since its last try job.

Like nacl_deps_bump.py, this tool should be run from a Git checkout of
Chromium.
"""

import optparse
import re
import subprocess
import time

import pysvn

import get_chromium_lkgr
import get_nacl_revs
import nacl_deps_bump


# When this number of new revisions accumulates, we kick off a new build.
REVS_THRESHOLD = 10

# When the last revision is this old, we kick off a new build.
TIME_THRESHOLD = 60 * 60 * 12 # 12 hours


# Returns a list of NaCl SVN revision numbers that we have already
# kicked off try jobs for.  This is based on the branch names in the
# current Git repo.  This is imperfect because we might have created a
# branch before but failed to send a try job for it.  We err on the
# side of not spamming the trybots.
def GetExistingJobs():
  proc = subprocess.Popen(['git', 'for-each-ref',
                           '--format', '%(refname:short)',
                           'refs/heads/*'], stdout=subprocess.PIPE)
  revs = []
  for line in proc.stdout:
    match = re.match('nacl-deps-r(\d+)$', line.strip())
    if match is not None:
      revs.append(int(match.group(1)))
  assert proc.wait() == 0, proc.wait()
  return revs


# Returns the time that the given SVN revision was committed, as a
# Unix timestamp.
def GetRevTime(svn_root, rev_num):
  rev = pysvn.Revision(pysvn.opt_revision_kind.number, rev_num)
  lst = pysvn.Client().log(svn_root, revision_start=rev, revision_end=rev)
  assert len(lst) == 1, lst
  return lst[0].date


def Main():
  parser = optparse.OptionParser('%prog\n\n' + __doc__.strip())
  options, args = parser.parse_args()
  if len(args) != 0:
    parser.error('Got unexpected arguments')

  last_tried_rev = max([1] + GetExistingJobs())
  print 'last tried NaCl revision is r%i' % last_tried_rev
  age = time.time() - GetRevTime(nacl_deps_bump.NACL_SVN_ROOT, last_tried_rev)
  print 'age of r%i: %.1f hours' % (last_tried_rev, age / (60 * 60))

  newest_rev = nacl_deps_bump.GetNaClRev()
  rev_diff = newest_rev - last_tried_rev
  print '%i revisions since last try' % rev_diff

  do_build = False
  if age > TIME_THRESHOLD:
    print 'time threshold passed: trigger new build'
    do_build = True
  # Note that this comparison ignores that the commits might be to
  # branches rather the trunk.
  if rev_diff > REVS_THRESHOLD:
    print 'revision count threshold passed: trigger new build'
    do_build = True

  # Check Chromium's LKGR to avoid bad try runs.
  last_deps_bump = get_nacl_revs.GetSvnLastDepsBump()
  print 'The last nacl_revision change in Chromium was in r%i' % last_deps_bump
  chromium_lkgr = get_chromium_lkgr.GetLkgr()
  print 'Chromium LKGR is r%i' % chromium_lkgr
  if chromium_lkgr >= last_deps_bump:
    print 'Chromium LKGR includes last nacl_revision change (good)'
  else:
    print 'Chromium LKGR has not caught up yet (bad)'
    # Don't attempt to run a new try job, because we generate a patch
    # against Chromium's latest revision which would fail to apply
    # against LKGR, which is what the trybots use by default.  We
    # could pass "-rHEAD" to the trybots, but then the trybots are
    # more likely to fail if we get a bad revision of Chromium.
    do_build = False

  if do_build:
    nacl_deps_bump.Main(['--revision', str(newest_rev)])


if __name__ == '__main__':
  Main()
