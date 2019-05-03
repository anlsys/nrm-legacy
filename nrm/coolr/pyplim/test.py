#!/usr/bin/env python

import sys
import plim_module

if (len(sys.argv) < 3): 
        print "Usage: test.py [pkgid] [powercapwatt]"
        sys.exit(0)


pkgid = int(sys.argv[1])
watt = float(sys.argv[2])

print 'pkgid: pkgid', pkgid
print 'powercap [W]', watt


plim_module.plim(pkgid, watt)

print 'done'
