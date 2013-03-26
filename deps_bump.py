# Copyright (c) 2013 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import re


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


def MatchKey(data, key):
  match = re.search('^\s*"%s":\s*"(\S+)",\s*(#.*)?$' % key, data, re.M)
  if match is None:
    raise Exception('Key %r not found' % key)
  return match


def GetDepsField(data, key):
  match = MatchKey(data, key)
  return match.group(1)


def SetDepsField(data, key, value):
  match = MatchKey(data, key)
  return ''.join([data[:match.start(1)],
                  value,
                  data[match.end(1):]])
