"""
.. module:: pathspider.chains.traceroute
   :synopsis: A flow analysis chain for traceroute messages especially icmp messages

"""

from pathspider.chains.base import Chain
from pathspider.traceroute_base import INITIAL_SEQ
import logging
#from pathspider.base import Spider
from straight.plugin import load

chain = load("pathspider.chains", subclasses=Chain)

#plug = PluggableSpider()
#current_plugin = plug.plugin()

# TODO PLUGIN works but I just take the one plugin with _trace:  ecn_trace???????????????

chosen_chains = []

for abc in chain:
        if "_trace" in abc.__name__.lower():
            chosen_chains.append(abc)

#: ICMPv4 Message Type - TTL Exceeded
ICMP4_TTLEXCEEDED = 11
#: ICMPv6 Message Type - Time Exceeded
ICMP6_TTLEXCEEDED = 3



class tracerouteChain(Chain):
    """
    This flow analysis chain is the basic chain for tracerouting 
    """
    
    #print(self.args)
    
    def new_flow(self, rec, ip):
         """
         For a new flow, all fields will be initialised to ``False`` or 0.
 
         :param rec: the flow record
         :type rec: dict
         :param ip: the IP or IPv6 packet that triggered the creation of a new
                    flow record
         :type ip: plt.ip or plt.ip6
         :return: Always ``True``
         :rtype: bool
         """
         
         rec['trace'] = False
         rec['hops'] = 0
         rec['_seq'] = 11000
         return True
        
    def ip4(self, rec, ip, rev):
        if ip.tcp and not rev: 
            self.dest_seq(rec, ip)
        if ip.tcp and rev:
            self.dest_trace(rec, ip, ip.icmp)
        return True
            
    def ip6(self, rec, ip6, rev):
        if ip6.tcp and not rev: 
            self.dest_seq(rec, ip6)
        if ip6.tcp and rev:
            self.dest_trace(rec, ip6, ip6.icmp6)
        return True
            
    def icmp4(self, rec, ip, q, rev):
        if rev and ip.icmp.type == ICMP4_TTLEXCEEDED:
            try:
                tcp_seq = ip.icmp.payload.tcp.seq_nbr  
            except AttributeError:
                print("IPv4 Sequence error")
            else:      
                self.trace(rec, ip, ip.icmp, tcp_seq)
        return True
    
    def icmp6(self, rec, ip6, q, rev):    
        if rev and ip6.icmp6.type == ICMP6_TTLEXCEEDED:
            try:
                tcp_payload = ip6.icmp6.payload.payload         
                tcp_seq = (tcp_payload[4]<<24)+(tcp_payload[5]<<16)+(tcp_payload[6]<<8)+tcp_payload[7]
            except AttributeError:
                print("IPv6 Sequence error")
            else:
                self.trace(rec, ip6, ip6.icmp6, tcp_seq)
        return True
        
    def dest_seq(self, rec, ip):
        """Outgoing packet IP and TCP header data for comparison in tracemerger"""
        data = ip.data 
        """Timestamp for calculating rtt in tracemerger"""              
        timeinit = ip.tcp.seconds
        """Sequence number to find the corresponding packets"""
        try:
            sequence = str(ip.tcp.seq_nbr)
            rec[sequence] = {'rtt': timeinit, 'data': data}
        except AttributeError:
            print("Sequence Attribute Error!")
          
        
    def dest_trace(self, rec, ip, icmp):
        """Hops used to reach destination to give to the ipqueue"""
        rec['hops'] = ip.ttl  
        """Acknowledge number of destination -1 is sequence number of received package"""
        seq_nbr = (ip.tcp.ack_nbr-1)                      

        """Calculating final hop with sequence number """
        if rec['_seq'] > seq_nbr and rec['_seq'] > 10000:
            final_hop = seq_nbr-INITIAL_SEQ
            rec['Destination'] = {'from': str(ip.src_prefix),'hops': final_hop}
            rec['_seq'] = seq_nbr
            
            """Conditions of chain for special measurements""" 
            if len(chosen_chains) > 0:
                for c in chosen_chains: 
                    ch = c()
                    if hasattr(ch, 'box_info'):
                        plugin_out = getattr(ch, "box_info")(ip, icmp)
                        rec['Destination']['conditions'] = plugin_out
    
    def trace(self, rec, ip, icmp, tcp_seq):
        
        """Packets should be merged by tracemerger"""
        rec['trace'] = True
        
        """Identification of hop number via sequence number""" #check if it works now... problem if icmp has no tcp??
        hopnumber = str(tcp_seq - (INITIAL_SEQ-1))
        
        """IP of middlebox"""
        box_ip = str(ip.src_prefix)
          
        """Packet arrival time for calculation of rtt in merger"""
        time = ip.seconds
                   
        """length of payload that comes back to identify RFC1812-compliant routers"""
        pp = icmp.payload.payload
        payload_len = len(pp)
         
        """payload data of returning packet for bitwise comparison in merger""" 
        data = icmp.payload.data
        
        rec[hopnumber] = {'from': box_ip, 'rtt': time, 'size': payload_len, 'data': data}
        
        """Additional 'conditions' info of additional plugin chains"""      
        if len(chosen_chains) > 0:
            for c in chosen_chains: 
                ch = c()
                if hasattr(ch, 'box_info'):
                    plugin_out = getattr(ch, "box_info")(ip, icmp)
                    rec[hopnumber]['conditions'] = plugin_out             
