#!/usr/bin/env python
# Copyright (c) 2012 The Native Client Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import time
import urllib2


# This script gets Chromium's LKGR value (Last Known Good Revision).
# We record the value in a log for posterity, because
# chromium-status.appspot.com does not appear to log it, or at least
# does not make the log available.


def GetLkgr():
  data = urllib2.urlopen('http://chromium-status.appspot.com/lkgr').read()
  lkgr_rev = int(data.strip())
  time_now = time.time()
  time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time_now))
  log_file = open('chromium_lkgr.log', 'a')
  log_file.write('%s,%s,%s\n' % (lkgr_rev, time_now, time_str))
  return lkgr_rev


if __name__ == '__main__':
  print GetLkgr()
