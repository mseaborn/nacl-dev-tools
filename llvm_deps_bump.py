#!/usr/bin/env python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import optparse
import os
import subprocess
import sys

from deps_bump import ReadFile, WriteFile, GetDepsField, SetDepsField


def GetCommandOutput(command, **kwargs):
  proc = subprocess.Popen(command, stdout=subprocess.PIPE, **kwargs)
  stdout = proc.communicate()[0]
  status = proc.wait()
  assert status == 0, (command, status)
  return stdout


def GetNewRev(git_dir):
  subprocess.check_call(['git', 'fetch'], cwd=git_dir)
  return GetCommandOutput(['git', 'rev-parse', 'origin/master'],
                          cwd=git_dir).strip()


def GetLog(git_dir, rev1, rev2):
  log_args = ['^' + rev1, rev2, '^origin/upstream/master']
  log_data = GetCommandOutput(['git', 'log', '--pretty=format:%h: (%ae) %s']
                              + log_args, cwd=git_dir)
  authors_data = GetCommandOutput(['git', 'log', '--pretty=%ae']
                                  + log_args, cwd=git_dir)
  full_log = GetCommandOutput(['git', 'log', '--pretty=%B']
                              + log_args, cwd=git_dir)
  log = '\n'.join(reversed(log_data.strip().split('\n'))) + '\n'
  authors = authors_data.strip().split('\n')
  bugs = []
  for line in reversed(full_log.split('\n')):
    if line.startswith('BUG='):
      bug = line[4:].strip()
      bug_line = 'BUG= %s\n' % bug
      if bug_line not in bugs and bug != 'none':
        bugs.append(bug_line)
  if len(bugs) == 0:
    bugs = ['BUG=none\n']
  return log, authors, ''.join(bugs)


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
  parser.add_option('-c', '--component', default='llvm', type='string',
                    help='Subdirectory of pnacl/git/ to update DEPS from')
  parser.add_option('-r', '--revision', default=None, type='string',
                    help='Git revision to use')
  parser.add_option('-u', '--no-upload', action='store_true', default=False,
                    help='Do not run "git cl upload" (implies --no-try)')
  parser.add_option('-T', '--no-try', action='store_true', default=False,
                    help='Do not start a trybot run')
  options, args = parser.parse_args(args)
  if len(args) != 0:
    parser.error('Got unexpected arguments')

  git_dir = os.path.join('pnacl/git', options.component)
  component_name = {'llvm': 'LLVM',
                    'clang': 'Clang'}[options.component]
  deps_field = {'llvm': 'pnacl_llvm_rev',
                'clang': 'clang_rev'}[options.component]

  AssertNoUncommittedChanges()

  new_rev = options.revision
  if new_rev is None:
    new_rev = GetNewRev(git_dir)

  subprocess.check_call(['git', 'fetch'])
  subprocess.check_call(['git', 'checkout', 'origin/master'])

  deps_file = 'pnacl/DEPS'
  deps_data = ReadFile(deps_file)
  old_rev = GetDepsField(deps_data, deps_field)
  if new_rev == old_rev:
    raise AssertionError('No new changes!')
  deps_data = SetDepsField(deps_data, deps_field, new_rev)
  WriteFile(deps_file, deps_data)

  msg_logs, authors, bugs = GetLog(git_dir, old_rev, new_rev)
  msg = 'PNaCl: Update %s revision in pnacl/DEPS' % component_name
  msg += '\n\nThis pulls in the following %s changes:\n\n' % component_name
  msg += msg_logs
  msg += '\n'
  msg += bugs
  msg += 'TEST=PNaCl toolchain trybots\n'
  print msg
  subprocess.check_call(['git', 'commit', '-a', '-m', msg])
  cc_list = ', '.join(sorted(set(authors)))
  print 'CC:', cc_list

  branch_name = '%s-deps-%s' % (options.component, new_rev[:8])
  subprocess.check_call(['git', 'checkout', '-b', branch_name])

  if options.no_upload:
    return
  environ = os.environ.copy()
  environ['EDITOR'] = 'true'
  # TODO(mseaborn): This can ask for credentials when the cached
  # credentials expire, so could fail when automated.  Can we fix
  # that?
  subprocess.check_call(['git', 'cl', 'upload', '-m', msg, '--cc', cc_list],
                        env=environ)
  if options.no_try:
    return
  subprocess.check_call(['git', 'try'])


if __name__ == '__main__':
  Main(sys.argv[1:])
