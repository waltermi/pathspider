
import argparse
import logging
import json
import queue
import signal
import sys
import threading
import time

from straight.plugin import load

from pathspider.base import SHUTDOWN_SENTINEL
from pathspider.base import QUEUE_SIZE

from pathspider.chains.base import Chain

from pathspider.observer import Observer

from pathspider.network import interface_up

from pathspider.traceroute_send import send_pkts

import multiprocessing as mp
from pathspider.base import SHUTDOWN_SENTINEL


chains = load("pathspider.chains", subclasses=Chain)

def run_traceroute(args):
    logger = logging.getLogger("pathspider")


    if not interface_up(args.interface):
        logger.error("The chosen interface is not up! Cannot continue.")
        logger.error("Try --help for more information.")
        sys.exit(1)

    logger.info("Creating observer...")

    chosen_chains = []
    
    """geht besser oder???"""    
    for abc in chains:
        if "traceroutechain" == abc.__name__.lower():
            chosen_chains.append(abc)


    """Setting up observer"""
    observer_shutdown_queue = queue.Queue(QUEUE_SIZE)
    flowqueue = queue.Queue(QUEUE_SIZE)
    observer = Observer("int:" + args.interface, chosen_chains)

    logger.info("Starting observer...")
    threading.Thread(target=observer.run_flow_enqueuer, args=(flowqueue,observer_shutdown_queue)).start()
    
    
    """Setting up sender"""
    ipqueue = mp.Queue(QUEUE_SIZE)
    
    inputfile = "ip_input.txt"       #TODO make this an input argument
    threading.Thread(target=queue_feeder, args=(inputfile, ipqueue)).start()
    #queue_feeder(inputfile, ipqueue)
    send = mp.Process(target=send_pkts,args=(args.hops,args.flows,ipqueue))
    send.start()

    logger.info("Opening output file " + args.output)
    with open(args.output, 'w') as outputfile:
        logger.info("Registering interrupt...")
        def signal_handler(signal, frame):          #ctrl-c shutdown
            observer_shutdown_queue.put(True)
        signal.signal(signal.SIGINT, signal_handler)
        
        signal.signal(signal.SIGALRM, signal_handler)  #shutdown after sender has finished               
        first = False
        
        while True:
            
            if not send.is_alive() and not first: #check if sender is finished but do only first time after finishing
                signal.alarm(3)
                first = True
      
            result = flowqueue.get()
                           
            if result == SHUTDOWN_SENTINEL:
                logger.info("Output complete")
                break
            
            #Only get the flows with the ttl_exceeded message and add timestamp
            result = filter(result)
            
            
            
            if result != []:
                outputfile.write(json.dumps(result) + "\n")
                logger.debug("wrote a result")

def filter(res): #TODO what happens when we get SHUTDOWN SENTINEL?
    
    #only icmp ttl_exceeded messages are wanted
    for entry in res:
        if entry == 'ttl_exceeded' and res[entry] == False:
            return []
            pas
    res2=res.copy()
    
    
    """delete unnecessary things and calculate round-trip time in milliseconds"""
    for entry in res.copy():
        if entry == 'ttl_exceeded' or entry == '_idle_bin' or entry == 'pkt_first' or entry == 'pkt_last':
                del res[entry]
        else:
            for entry2 in res.copy():
                diff = bytearray()
                if entry2 == 'ttl_exceeded' or entry2 == '_idle_bin' or entry2 == 'pkt_first' or entry2 == 'pkt_last':
                    del entry2
                elif (int(entry)+9999) == int(entry2):  #comparing sequencenumber of upstream entry2 with hopnumber of downstream entry
                    rtt= (res[entry][1]- res[entry2][0])*1000
                    rtt = round(rtt,3)
                    
                    """bytearray comparison still doesn't work properly -.-"""
                    #for i in range(15):
                     #   diff = diff + bytearray(res[entry][3][i]^res[entry2][1][i])
                    
                    #diff = bytearray(res[entry][3][0]^res[entry2][1][0])
                    res[entry] = [res[entry][0], rtt, res[entry][2], res[entry][3]]#, str(diff)]#str(res[entry][3]), str(res[entry2][1])]
                    del res[entry2]
    
    # remove sequence number entries that have not been used                
    for entrytest in res.copy():
        if int(entrytest) > 100:
            del res[entrytest]
                
    return res.copy()

def queue_feeder(inputfile, ipqueue):
    with open(inputfile) as fh:
        for line in fh:
            try:
                job = json.loads(line)
                if 'dip' in job.keys():
                    ipqueue.put(job['dip'])
            except ValueError:
                pass
    ipqueue.put(SHUTDOWN_SENTINEL)


       
def register_args(subparsers):
    class SubcommandHelpFormatter(argparse.RawDescriptionHelpFormatter):
        def _format_action(self, action):
            parts = super()._format_action(action)
            if action.nargs == argparse.PARSER:
                parts = "\n".join([line for line in parts.split("\n")[1:]])
                parts += "\n\nSpider safely!"
            return parts

    parser = subparsers.add_parser(name='traceroute',help="Perform a traceroute",
                                   formatter_class=SubcommandHelpFormatter)
    parser.add_argument('IP', type = str, help="IP or URL for which traceroute should be performed")
    parser.add_argument('hops', type = int, help="Number of hops to destination IP")
    parser.add_argument('-i', '--interface', default="eth0",
                        help="The interface to use for the observer. (Default: eth0)")
    parser.add_argument('-f','--flows', type = int, default = 1, 
                        help="Number of times the traceroute should be conducted with different flows. (Default: 1)")
    parser.add_argument('--output', default='/dev/stdout', metavar='OUTPUTFILE',
                        help=("The file to output results data to. "
                              "Defaults to standard output."))
    

    # Set the command entry point
    parser.set_defaults(cmd=run_traceroute)
