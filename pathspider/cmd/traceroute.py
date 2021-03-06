
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
from pathspider.base import QUEUE_SLEEP

from pathspider.chains.base import Chain

from pathspider.observer import Observer

from pathspider.network import interface_up

from pathspider.traceroute_base import traceroute

import multiprocessing as mp

HOPS = 40


chains = load("pathspider.chains", subclasses=Chain)

def run_traceroute(args):
    logger = logging.getLogger("pathspider")


    if not interface_up(args.interface):
        logger.error("The chosen interface is not up! Cannot continue.")
        logger.error("Try --help for more information.")
        sys.exit(1)

    """Check if inputfile or single IP was given as an input argument"""    
    if args.input != 'null':
        file = True
    elif args.ip != 'null':
        file = False
    else:
        logger.error('Please chose either an inputfile or a single IP to traceroute')
        sys.exit(1)

    
    logger.info("Creating observer...")

    chosen_chains = []
    
    """geht besser oder???"""   #Auch wichtig noch möglich machen für andere extensions, dh hinzufügen von auswahlmöglichkeit in cmdline 
    for abc in chains:
        if "traceroutechain" == abc.__name__.lower():
            chosen_chains.append(abc)
        if "basicchain" == abc.__name__.lower():
            chosen_chains.append(abc)

    """Setting up observer"""
    observer_shutdown_queue = queue.Queue(QUEUE_SIZE)
    flowqueue = queue.Queue(QUEUE_SIZE)
    resultqueue = queue.Queue(QUEUE_SIZE)
    observer = Observer("int:" + args.interface, chosen_chains)

    logger.info("Starting observer...")
    threading.Thread(target=observer.run_flow_enqueuer, args=(flowqueue,observer_shutdown_queue),daemon = True).start()
    
    mergequeue = queue.Queue(QUEUE_SIZE)
    threading.Thread(target = filter, args=(flowqueue, mergequeue), daemon = True).start()
    
    trace = traceroute()
    
    """ Setting up merger"""
    logger.info("Starting merger...")
    outqueue = queue.Queue(QUEUE_SIZE)
    merge = threading.Thread(target=trace.trace_merger, args=(mergequeue, outqueue), daemon = True)
    merge.start()
    
    """Setting up sender"""
    logger.info("Starting sender...")
    ipqueue = mp.Queue(QUEUE_SIZE) 
    send = mp.Process(target=trace.sender, args=(ipqueue, args.flows), daemon = True)
    send.start()
    
    """Read ips to file and add them to ipqueue for sender, if no file, just put single ip"""
    if file:
        logger.info("Starting queue feeder")
        threading.Thread(target=queue_feeder, args=(args.cond, args.input, ipqueue, args.hops), daemon = True).start()
    else:
        inp = {'dip': args.ip, 'hops': args.hops}
        ipqueue.put(inp)
        ipqueue.put(SHUTDOWN_SENTINEL)

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
            
            try:
                result = outqueue.get_nowait()
            except queue.Empty:
                time.sleep(QUEUE_SLEEP)
            else:
                   
                if result == SHUTDOWN_SENTINEL:
                    logger.info("Output complete")
                    break

                outputfile.write(json.dumps(result) + "\n")
                logger.debug("wrote a result")

def filter(res, merge): #Only flows with trace flag should go to merger
    while True:
        entry = res.get()
        
        if entry == SHUTDOWN_SENTINEL:
            merge.put(SHUTDOWN_SENTINEL)
            break
        try:
            if entry['trace'] == True:
                merge.put(entry)
        except KeyError:
            pass

def queue_feeder(cond, inputfile, ipqueue, inputhops): #needs work, some stuff is unnecessary!!!
    logger = logging.getLogger("pathspider")
    seen_targets = set()
    with open(inputfile) as fh:
        for line in fh:
            job = json.loads(line)
            try:    #check for 'dip' key in job
                dip = job['dip']
            except KeyError:
                logger.warning("Entry does not contain 'dip', skipping")
                continue
            
            if job['dip'] in seen_targets:
                    logger.debug("This target has already had a job submitted, skipping.")
                    continue
            try:    #check for 'hops' key in job
                hop = job['hops']
            except KeyError:
                logger.debug("Entry does not contain 'hops', taking default")
                hop = inputhops
            
            inp = {'dip': dip, 'hops': hop}
            
            if cond != None:   #Check if condition in cmd line is given for tracerouting
                try:    
                    if cond in job['conditions']:
                        ipqueue.put(inp)
                        logger.debug("added job")
                        seen_targets.add(dip)
                except KeyError:
                    logger.debug("Job has no 'conditions' list, skipping")
                    continue
            else:
                ipqueue.put(inp)
                logger.debug("added job")
                seen_targets.add(dip)
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
    parser.add_argument('-hops', type = int, help="Number of hops to destination IP (Default: %i)"%HOPS, default = HOPS)
    parser.add_argument('-i', '--interface', default="eth0",
                        help="The interface to use for the observer. (Default: eth0)")
    parser.add_argument('-f','--flows', type = int, default = 3, 
                        help="Number of times the traceroute should be conducted with different flows. (Default: 3)")
    parser.add_argument('-cond', type = str, default = None, help="Condition in inputfile for doing tracerouting")
    parser.add_argument('--ip', type = str, default = 'null', help="IP for which traceroute should be performed")
    parser.add_argument('--input', default='null', metavar='INPUTFILE', help=("A file containing a list of IPs to traceroute. "
                              "Defaults to standard input."))
    parser.add_argument('--output', default='/dev/stdout', metavar='OUTPUTFILE',
                        help=("The file to output results data to. "
                              "Defaults to standard output."))
    

    # Set the command entry point
    parser.set_defaults(cmd=run_traceroute)
