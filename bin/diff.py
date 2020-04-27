from __future__ import print_function
from builtins import str
import os
import time
import sys
import xml.dom.minidom, xml.sax.saxutils
import logging

import difflib
import subprocess
import itertools
import re
import pickle

#set up logging suitable for splunkd comsumption
logging.root
logging.root.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(levelname)s %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.root.addHandler(handler)

SCHEME = """<scheme>
    <title>Btool Diff</title>
    <description>Index Btool differences</description>
    <use_external_validation>false</use_external_validation>
    <streaming_mode>xml</streaming_mode>

    <endpoint>
        <args>
            <arg name="conf">
                <title>Config File</title>
                <description>Which config file to compare.</description>
                <data_type>string</data_type>
                <validation>
                validate(conf in ("authentication","authorize", "indexes", "inputs", "limits", "outputs", "props", "rolemap", "saml", "server", "transforms", "web", "app"), "Invalid Config File")
                </validation>
                <required_on_create>true</required_on_create>
            </arg>
            <arg name="app">
                <title>App</title>
                <description>App Context.</description>
                <data_type>string</data_type>
                <required_on_create>false</required_on_create>
            </arg>
            <arg name="user">
                <title>User</title>
                <description>User Context.</description>
                <data_type>string</data_type>
                <required_on_create>false</required_on_create>
            </arg>
        </args>
    </endpoint>
</scheme>
"""

def validate_conf(config, key):
    if key not in config:
        raise Exception("Invalid configuration received from Splunk: key '%s' is missing." % key)

# Routine to get the value of an input
def get_config():
    config = {}

    try:
        # read everything from stdin
        config_str = sys.stdin.read()

        # parse the config XML
        doc = xml.dom.minidom.parseString(config_str)
        root = doc.documentElement
        conf_node = root.getElementsByTagName("configuration")[0]
        if conf_node:
            logging.debug("XML: found configuration")
            stanza = conf_node.getElementsByTagName("stanza")[0]
            if stanza:
                stanza_name = stanza.getAttribute("name")
                if stanza_name:
                    logging.debug("XML: found stanza " + stanza_name)
                    config["name"] = stanza_name

                    params = stanza.getElementsByTagName("param")
                    for param in params:
                        param_name = param.getAttribute("name")
                        logging.debug("XML: found param '%s'" % param_name)
                        if param_name and param.firstChild and \
                           param.firstChild.nodeType == param.firstChild.TEXT_NODE:
                            data = param.firstChild.data
                            config[param_name] = data
                            logging.debug("XML: '%s' -> '%s'" % (param_name, data))

        checkpnt_node = root.getElementsByTagName("checkpoint_dir")[0]
        if checkpnt_node and checkpnt_node.firstChild and \
           checkpnt_node.firstChild.nodeType == checkpnt_node.firstChild.TEXT_NODE:
            config["checkpoint_dir"] = checkpnt_node.firstChild.data

        if not config:
            raise Exception("Invalid configuration received from Splunk.")

        validate_conf(config, "conf")

    except Exception as e:
        raise Exception("Error getting Splunk configuration via STDIN: %s" % str(e))

    return config

# Routine to index data
def run_script():
    config = get_config()
    source = config["conf"]
    splunk_exe = os.path.join(os.environ['SPLUNK_HOME'], 'bin', 'splunk')

    checkpoint = os.path.join(config["checkpoint_dir"],source)

    try:
        old = pickle.load(open(checkpoint,"r"))
    except:
        old = False

    new = []
    config = subprocess.check_output([splunk_exe,"btool",source,"list"]).split('\n')
    stanzas = subprocess.check_output([splunk_exe,"btool","--debug-print=stanza",source,"list"]).split('\n')
    files = subprocess.check_output([splunk_exe,"btool","--debug-print=sourcefile",source,"list"]).split('\n')

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
        print("<stream>")
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
                        print("<event><source>{}</source><sourcetype>btooldiff</sourcetype><data>action=\"changed\" stanza=\"{}\" key=\"{}\" old_value=\"{}\" old_file=\"{}\" old_default=\"{}\" new_value=\"{}\" new_file=\"{}\" new_default=\"{}\"</data></event>".format(source,new[n][0],new[n][1],old[o][2],old[o][3],old[o][4],new[n][2],new[n][3],new[n][4]))
                    n+=1
                    o+=1
                elif new[n][1] < old[o][1]: 
                    #Added Key
                    print("<event><source>{}</source><sourcetype>btooldiff</sourcetype><data>action=\"added\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"</data></event>".format(source,new[n][0],new[n][1],new[n][2],new[n][3],new[n][4]))
                    n+=1
                else: #elif new[n][1] > old[o][1]: 
                    #Removed Key
                    print("<event><source>{}</source><sourcetype>btooldiff</sourcetype><data>action=\"removed\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"</data></event>".format(source,old[o][0],old[o][1],old[o][2],old[o][3],old[o][4]))
                    o+=1
            elif new[n][0] < old[o][0]: 
                #Added Stanza
                print("<event><source>{}</source><sourcetype>btooldiff</sourcetype><data>action=\"added\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"</data></event>".format(source,new[n][0],new[n][1],new[n][2],new[n][3],new[n][4]))
                n+=1
            else: #elif new[n][0] > old[o][0]: 
                #Removed Stanza
                print("<event><source>{}</source><sourcetype>btooldiff</sourcetype><data>action=\"removed\" stanza=\"{}\" key=\"{}\" value=\"{}\" file=\"{}\" default=\"{}\"</data></event>".format(source,old[o][0],old[o][1],old[o][2],old[o][3],old[o][4]))
                o+=1
        print("</stream>")

    pickle.dump(new,open(checkpoint,"w"))
 
# Script must implement these args: scheme, validate-arguments
if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == "--scheme":
            print(SCHEME)
        elif sys.argv[1] == "--validate-arguments":
            pass
        else:
            pass
    else:
        run_script()

    sys.exit(0)