#!/usr/bin/env python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import optparse
import os
import subprocess
import sys

from nacl_deps_bump import ReadFile, WriteFile, GetDepsField, SetDepsField
import nacl_deps_bump


LLVM_DIR = 'pnacl/git/llvm'


def GetCommandOutput(command, **kwargs):
  proc = subprocess.Popen(command, stdout=subprocess.PIPE, **kwargs)
  stdout = proc.communicate()[0]
  status = proc.wait()
  assert status == 0, (command, status)
  return stdout


def GetNewRev():
  subprocess.check_call(['git', 'fetch'], cwd=LLVM_DIR)
  return GetCommandOutput(['git', 'rev-parse', 'origin/master'],
                          cwd=LLVM_DIR).strip()


def GetLog(rev1, rev2):
  log_args = ['^' + rev1, rev2, '^origin/upstream/master']
  log_data = GetCommandOutput(['git', 'log', '--pretty=format:%h: (%ae) %s']
                              + log_args, cwd=LLVM_DIR)
  authors_data = GetCommandOutput(['git', 'log', '--pretty=%ae']
                                  + log_args, cwd=LLVM_DIR)
  log = '\n'.join(reversed(log_data.strip().split('\n'))) + '\n'
  authors = authors_data.strip().split('\n')
  return log, authors


def AssertNoUncommittedChanges():
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


def Main(args):
  parser = optparse.OptionParser()
  parser.add_option('-r', '--revision', default=None, type='string',
                    help='LLVM Git revision to use')
  options, args = parser.parse_args(args)
  if len(args) != 0:
    parser.error('Got unexpected arguments')

  AssertNoUncommittedChanges()

  new_rev = options.revision
  if new_rev is None:
    new_rev = GetNewRev()

  subprocess.check_call(['git', 'fetch'])
  subprocess.check_call(['git', 'checkout', 'origin/master'])

  deps_file = 'pnacl/DEPS'
  deps_field = 'pnacl_llvm_rev'
  deps_data = ReadFile(deps_file)
  old_rev = GetDepsField(deps_data, deps_field)
  if new_rev == old_rev:
    raise AssertionError('No new changes!')
  deps_data = SetDepsField(deps_data, deps_field, new_rev)
  WriteFile(deps_file, deps_data)

  msg_logs, authors = GetLog(old_rev, new_rev)
  msg = 'PNaCl: Update LLVM revision in pnacl/DEPS'
  msg += '\n\nThis pulls in the following LLVM changes:\n\n'
  msg += msg_logs
  msg += '\nBUG=none\n'
  msg += 'TEST=PNaCl toolchain trybots\n'
  print msg
  subprocess.check_call(['git', 'commit', '-a', '-m', msg])
  cc_list = ', '.join(sorted(set(authors)))
  print 'CC:', cc_list

  branch_name = 'llvm-deps-%s' % new_rev[:8]
  subprocess.check_call(['git', 'checkout', '-b', branch_name])

  environ = os.environ.copy()
  environ['EDITOR'] = 'true'
  # TODO(mseaborn): This can ask for credentials when the cached
  # credentials expire, so could fail when automated.  Can we fix
  # that?
  subprocess.check_call(['git', 'cl', 'upload', '-m', msg, '--cc', cc_list],
                        env=environ)
  subprocess.check_call(['git', 'try'])


if __name__ == '__main__':
  Main(sys.argv[1:])
