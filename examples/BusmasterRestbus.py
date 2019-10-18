#!/usr/bin/env python2
# Copyright (c) 2013, Eduard Broecker
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that
# the following conditions are met:
#
#    Redistributions of source code must retain the above copyright notice, this list of conditions and the
#    following disclaimer.
#    Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
#    following disclaimer in the documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE.

from __future__ import division
import math
from struct import *
import zipfile
import sys
sys.path.append('..')
import canmatrix.formats

import os

import glob
import string


def genString(string):
    retStr = "%c" % len(string)
    retStr += string
    return retStr


def genZeros(count):
    retStr = ""
    for i in range(count):
        retStr += "\x00"
    return retStr


def genSimulatonFile(nodes):
    # header
    retStr = "ff\xA6\x3F"
    retStr += genString("RBEI_FRAME")
    retStr += genString("CAN")
    retStr += genString("1.8.0")

    # count of nodes:
    retStr += "%c" % len(nodes)
    retStr += genZeros(4)

    # each node
    for (nodename, source) in list(nodes.items()):
        retStr += genString(source).encode('ascii')
        retStr += genString(nodename).encode('ascii')
        retStr += genZeros(10)

    # checksum
    temp = 0
    for c in retStr:
        ibyte = unpack('B', c)
        temp = (temp ^ ibyte[0])
    retStr = retStr[:-1] + "%c" % temp
    return retStr


def createNode(structNames, timedPrototypes, timedCallbacks):
    nodetemplate = """
/* This file is generated by BUSMASTER */
/* VERSION [1.1] */
/* BUSMASTER VERSION [1.8.0] */
/* PROTOCOL [CAN] */

/* Start BUSMASTER include header */
#include <Windows.h>
#include <CANIncludes.h>

/* End BUSMASTER include header */


/* Start BUSMASTER global variable */
"""

    nodetemplate2 = """
/* End BUSMASTER global variable */

/* Start BUSMASTER Function Prototype  */
"""
    return nodetemplate + structNames + nodetemplate2 + timedPrototypes + \
        "/* End BUSMASTER Function Prototype  */\n" + timedCallbacks


def genCallbacks(cycle, bId, db):
    botsch = db.frames.byId(bId).name
    callbacks = "/* Start BUSMASTER generated function - OnTimer_" + \
        botsch + "_" + str(cycle) + " */\n"
    callbacks += "void OnTimer_" + botsch + "_" + str(cycle) + "( )\n"
    callbacks += "{\n"

    canData = db.frames.byId(bId).attributes["GenMsgStartValue"][1:-2]
    dlc = math.floor(len(canData) / 2)
    callbacks += "    SendMsg(" + botsch + ");\n"
    callbacks += "\n} "
    callbacks += "/* End BUSMASTER generated function - OnTimer_" + \
        botsch + "_" + str(cycle) + " */\n\n"
    prototype = "GCC_EXTERN void GCC_EXPORT OnTimer_" + \
        botsch + "_" + str(cycle) + "( );\n"
    structNames = "STCAN_MSG " + botsch + \
        " = { " + hex(bId) + ", 0, 0, " + \
        str(math.floor(len(canData) / 2)) + ", 1,"
    for i in range(dlc):
        structNames += " 0x" + canData[i * 2:i * 2 + 2]
        if i < dlc - 1:
            structNames += ", "
    exports = "OnTimer_" + botsch + "_" + str(cycle) + "\n"

    structNames += "};\n"

    return structNames, prototype, callbacks, exports

exportTemplate = """EXPORTS
vSetEnableLoggingProcAddress
vSetDisableLoggingProcAddress
vSetWriteToLogFileProcAddress
vSetConnectProcAddress
vSetDisconnectProcAddress
vSetGoOnlineProcAddress
vSetGoOfflineProcAddress
vSetStartTimerProcAddress
vSetStopTimerProcAddress
vSetSetTimerValProcAddress
vSetEnableMsgHandlersProcAddress
vSetEnableErrorHandlersProcAddress
vSetEnableKeyHandlersProcAddress
vSetEnableDisableMsgTxProcAddress
vSetSendMsgProcAddress
vSetGetDllHandleProcAddress
vSetTraceProcAddress
vSetResetControllerProcAddress
bGetProgramVersion
vSetKeyPressed
vSetGetMessageName
vSetTimeNow
vSetGetFirstCANdbName

"""


def ticker_ecus(db, dbcname):
    nodeList = {}
    zf = zipfile.ZipFile(dbcname + '_Simulation.zip',
                         mode='w',
                         compression=zipfile.ZIP_DEFLATED,
                         )

    MyBuList = []

    for bu in db.ecus:
        if bu.name not in MyBuList:
            MyBuList.append(bu.name)  # no duplicate Nodes
        else:
            continue
        bu._cycles = {}
        for frame in db.frames:
            if bu.name in frame.transmitters:
                if frame.effective_cycle_time != 0 and "GenMsgStartValue" in frame.attributes:
                    data = frame.attributes["GenMsgStartValue"][1:-2]
                    dlc = (math.floor(len(data) / 2))
                    cycleTime = frame.effective_cycle_time
                    if float(cycleTime) > 0:
                        if cycleTime in bu._cycles:
                            bu._cycles[cycleTime].append(frame.arbitration_id.id)
                        else:
                            bu._cycles[cycleTime] = [frame.arbitration_id.id]
        nodeList[bu.name] = bu.name + ".cpp"

        timedPrototypes = ""
        timedCallbacks = ""
        structNames = ""
        exports = ""
        for cycle in bu._cycles:
            for frame in bu._cycles[cycle]:
                (tempstructNames, tempPrototypes, tempCallbacks,
                 tempExports) = genCallbacks(cycle, frame, db)
                structNames += tempstructNames
                timedPrototypes += tempPrototypes
                timedCallbacks += tempCallbacks
                exports += tempExports

        nodeString = createNode(structNames, timedPrototypes, timedCallbacks)

        zf.writestr(bu.name + ".cpp", nodeString)
        zf.writestr(bu.name + ".def", exportTemplate + exports)
    zf.writestr(dbcname + '.sim', genSimulatonFile(nodeList))
    zf.close()


def main():
    if len(sys.argv) < 3:
        sys.stderr.write('Usage: sys.argv[0] import-file export-file\n')
        sys.stderr.write('import-file: *.dbc|*.dbf|*.kcd\n')
        sys.stderr.write('export-file: somefile.zip\n')
        sys.exit(1)

    infile = sys.argv[1]
    outfile = os.path.splitext(sys.argv[2])[0]

    db = next(iter(canmatrix.formats.loadp(infile).values()))
    ticker_ecus(db, outfile)

main()
