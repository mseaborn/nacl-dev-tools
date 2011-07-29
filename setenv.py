#!/usr/bin/python

import os
import sys


def main(args):
    fh = open(args[0])
    for line in fh:
        if "=" not in line:
            raise Exception("Bad line: %r" % line)
        key, val = line.rstrip("\n").split("=", 2)
        os.environ[key] = val
    fh.close()
    os.execvp(args[1], args[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
