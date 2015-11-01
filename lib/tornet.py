#!/usr/bin/python
# This is distributed under cc0. See the LICENCE file distributed along with
# this code.

"""
   Let's simulate a tor network!  We're only going to do enough here
   to try out guard selection/replacement algorithms from proposal
   259, and some of its likely variants.
"""

import random

class Node:
    def __init__(self, name, port, evil=False, reliability=0.999):
        """Create a new Tor node."""

        # name for this node.
        self._name = name

        # What port does this node expose?
        assert 1 <= port <= 65535
        self._port = port

        # Is this a hostile node?
        self._evil = evil

        # How much of the time is this node running?
        self._reliabilitiy = 0.999

        # True if this node is running
        self._up = True

        # True if this node has been killed permanently
        self._dead = False

        # random hex string.
        self._id = "".join(random.choice("0123456789ABCDEF") for _ in xrange(40))

    def getName(self):
        """Return the human-readable name for this node."""
        return self._name

    def getID(self):
        """Return the hex id for this node"""
        return self._id

    def updateRunning(self):
        """Enough time has passed that some nodes are no longer running.
           Update this node randomly to see if it has come up or down."""

        # XXXX Actually, it should probably take down nodes a while to
        # XXXXX come back up.  I wonder if that matters for us.

        if not self._dead:
            self._up = random.random() < self._reliability

    def kill(self):
        """Mark this node as completely off the network, until resurrect
           is called."""
        self._dead = True
        self._up = False

    def resurrect(self):
        """Mark this node as back on the network."""
        self._dead = False
        self.updateRunning()

    def getPort(self):
        """Return this node's ORPort"""
        return self._port

    def isReallyUp(self):
        """Return true iff this node is truly alive.  Client simulation code
           mustn't call this."""
        return self._up

    def isReallyEvil(self):
        """Return true iff this node is truly evil.  Client simulation code
           mustn't call this."""
        return self._evil

def _randport(pfascistfriendly):
    """generate and return a random port.  If 'pfascistfriendly' is true,
       return a port in the FascistPortList.  Otherwise return any random
       TCP  port."""
    if random.random() < pfascistfriendly:
        return random.choice([80, 443])
    else:
        return random.randint(1,65535)

class Network:

    """Base class to represent a simulated Tor network.  Very little is
       actually simulated here: all we need is for guard nodes to come
       up and down over time.

       In this simulation, we ignore bandwidth, and consider every
       node to be a guard.  This shouldn't affect the algorithm.
    """
    def __init__(self, num_nodes, pfascistfriendly=.3, pevil=0.5,
                 avgnew=2.5, avgdel=2):

        """Create a new network with 'num_nodes' randomly generated nodes.
           Each node should be fascist-friendly with probability
           'pfascistfriendly'.  Each node should be evil with
           probability 'pevil'.  Every time the network churns,
           'avgnew' nodes should be added on average, and 'avgdel'
           deleted on average.
        """
        self._pfascistfriendly = pfascistfriendly
        self._pevil = pevil

        # a list of all the Nodes on the network, dead and alive.
        self._wholenet = [ Node("node%d"%n,
                                port=_randport(pfascistfriendly),
                                evil=random.random() < pevil)
                           for n in xrange(num_nodes) ]
        for node in self._wholenet:
            node.updateRunning()

        # lambda parameters for our exponential distributions.
        self._lamdbaAdd = 1.0 / avgnew
        self._lamdbaDel = 1.0 / avgdel

        # total number of nodes ever added on the network.
        self._total = n

    def new_consensus(self):
        """Return a list of the running guard nodes."""
        return [ node for node in self._wholenet if node.isReallyUp() ]

    def do_churn(self):
        """Simulate churn: delete and add nodes from/to the network."""
        nAdd = int(random.expovariate(self._lamdbaAdd) + 0.5)
        nDel = int(random.expovariate(self._lamdbaDel) + 0.5)

        # kill nDel non-dead nodes at random.
        random.shuffle(self._wholenet)
        nkilled = 0
        for node in self._wholenet:
            if nkilled == nDel:
                break
            if not node._dead:
                node.kill()
                nkilled += 1

        # add nAdd new nodes.
        for n in xrange(self._total, self._total+nAdd):
            node = Node("node%d"%n,
                        port=_randport(self._pfascistfriendly),
                        evil=random.random() < self._pevil)
            self._total += 1

        # update which nodes are running.
        for node in self._wholenet:
            node.updateRunning()

    def updateRunning(self):
        """Enough time has passed for some nodes to go down and some to come
           up."""
        for node in self._wholenet:
            node.updateRunning()

    def probe_node_is_up(self, node):
        """Called when a simulated client is trying to connect to 'node'.
           Returns true iff the connection succeeds."""
        return node.isReallyUp()


class _NetworkDecorator:
    """Decorator class for Network: wraps a network and implements all its
       methods by calling down to the base network.  We use these to
       simulate a client's local network connection."""

    def __init__(self, network):
        self._network = network

    def new_consensus(self):
        return self._network.new_consensus()

    def do_churn(self):
        self._network.do_churn()

    def probe_node_is_up(self, node):
        return self._network.probe_node_is_up(node)

    def updateRunning(self):
        self.updateRunning()

class FascistNetwork(_NetworkDecorator):
    """Network that blocks all connections except those to ports 80, 443"""
    def probe_node_is_up(self, node):
        return (node.getPort() in [80,443] and
                self._network.probe_node_is_up(node))

class EvilFilteringNetwork(_NetworkDecorator):
    """Network that blocks connections to non-evil nodes with P=pBlockGood"""
    def __init__(self, network, pBlockGood=1.0):
        super().__init__(network)
        self._pblock = pBlockGood

    def probe_node_is_up(self, node):
        if not node.isReallyEvil():
            if random.random() < self._pblock:
                return False
        return self._network.probe_node_is_up(node)

class EvilKillingNetwork(_NetworkDecorator):

    """Network that does a DoS attack on a client's non-evil nodes with
       P=pKillGood after each connection."""
    def __init__(self, network, pKillGood=1.0):
        super().__init__(network)
        self._pkill = pKillGood

    def probe_node_is_up(self, node):
        result = self._network.probe_node_is_up(node)

        if not node.isReallyEvil() and random.random() < self._pkill:
            node.kill()

        return result

class FlakyNetwork(_NetworkDecorator):
    """A network where all connections succ3eed only with probability
       'reliability', regardless of whether the node is up or down."""
    def __init__(self, network, reliability=0.9):
        super().__init__(network)
        self._reliability = reliability

    def probe_node_is_up(self, node):
        if random.random() >= self._reliability:
            return False
        return self._network.probe_node_is_up(node)
