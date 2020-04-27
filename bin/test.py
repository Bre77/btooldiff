from __future__ import print_function
from builtins import str
import os
import time
import sys

import difflib
import subprocess
import itertools
import re
import pickle

splunk_exe = os.path.join(os.environ['SPLUNK_HOME'], 'bin', 'splunk')
target = "props"

checkpoint = os.path.join("./etc/apps/btooldiff/bin",target)
try:
    old = pickle.load(open(checkpoint,"r"))
except:
    old = False

new = []
config = subprocess.check_output([splunk_exe,"btool",target,"list"]).split('\n')
stanzas = subprocess.check_output([splunk_exe,"btool","--debug-print=stanza",target,"list"]).split('\n')
files = subprocess.check_output([splunk_exe,"btool","--debug-print=sourcefile",target,"list"]).split('\n')

stanza_width = re.compile("^\S+\s+").match(stanzas[0]).end()-1

# Code from https://github.com/MattUebel/TA-runbtool/blob/master/bin/run_btool.py
for c, s, f in itertools.izip_longest(config, stanzas, files):
    c_split = c.split('=')
    c_name = c_split[0].strip()
    if len(c_split) == 2:
        c_value = c_split[1].strip()
    elif len(c_split) == 1:
        c_value = None
    else:
        c_value = "=".join(c_split[1:]).strip()
    f_name = re.compile("(?<=(\.conf))\s+").split(f)[0]
    s_name = s[:stanza_width].strip()
    if s_name == "default":
        new.append([new[-1][0],c_name,c_value,f_name,True])
    else:
        new.append([s_name,c_name,c_value,f_name,False])

if(old):
    o = 0
    n = 0
    while o < len(old) and n < len(new):

        if new[n][0] == old[o][0]: 
            #Same Stanza
            if new[n][1] == old[o][1]:
                #Same Key
                if new[n][2] == old[o][2]:
                    #Same Value
                    pass
                else:
                    #Changed Value
                    print("action=\"changed\" stanza=\"{}\" key=\"{}\" old_value=\"{}\" old_file=\"{}\" old_default=\"{}\" new_value=\"{}\" new_file=\"{}\" new_default=\"{}\"".format(new[n][0],new[n][1],old[o][2],old[o][3],old[o][4],new[n][2],new[n][3],new[n][4]))
                n+=1
                o+=1
            elif new[n][1] < old[o][1]: 
                #Added Key
                print("action=\"added\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"".format(new[n][0],new[n][1],new[n][2],new[n][3],new[n][4]))
                n+=1
            elif new[n][1] > old[o][1]: 
                #Removed Key
                print("action=\"removed\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"".format(old[o][0],old[o][1],old[o][2],old[o][3],old[o][4]))
                o+=1
            else:
                #WTF
                throw("WTF")
        elif new[n][0] < old[o][0]: 
            #Added Stanza
            print("action=\"added\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"".format(new[n][0],new[n][1],new[n][2],new[n][3],new[n][4]))
            n+=1
        elif new[n][0] > old[o][0]: 
            #Removed Stanza
            print("action=\"removed\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"".format(old[o][0],old[o][1],old[o][2],old[o][3],old[o][4]))
            o+=1
        else:
            #WTF
            throw("WTF")

pickle.dump(new,open(checkpoint,"w"))