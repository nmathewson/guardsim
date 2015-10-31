
import random

import simtime
import tornet

class GivingUp(Exception):
    pass

class Params:
    """
       Represents the configuration parameters of the client algorithm,
       as given in proposals 259 and 241
    """
    def __init__(self,
                 PRIMARY_GUARDS=3,
                 UTOPIC_GUARDS_THRESHOLD=3,
                 DYSTOPIC_GUARDS_THRESHOLD=3,

                 TOO_MANY_GUARDS=6,
                 TOO_RECENTLY=86400):
        self.PRIMARY_GUARDS = PRIMARY_GUARDS
        self.UTOPIC_GUARDS_THRESHOLD = UTOPIC_GUARDS_THRESHOLD
        self.DYSTOPIC_GUARDS_THRESHOLD = DYSTOPIC_GUARDS_THRESHOLD
        self.TOO_MANY_GUARDS = TOO_MANY_GUARDS
        self.TOO_RECENTLY = TOO_RECENTLY

class Guard:
    """
       Represents what a client knows about a guard.
    """
    def __init__(self, node):
        self._node = node
        self._markedDown = False
        self._markedUp = False
        self._tried = False
        self._addedAt = simtime.now()

    def getNode(self):
        return self._node

    def mark(self, up):
        self._tried = True
        if up:
            self._markedDown = False
            self._markedUp = True
        else:
            self._markedDown = True
            self._markedUp = False

    def canTry(self):
        return not (self._tried and self._markedDown)

    def markForRetry(self):
        self._tried = False

    def addedWithin(self, nSec):
        return self._addedAt + nSec >= simtime.now()

class Client:
    """
       A stateful client implementation of the guard selection algorithm.
    """
    def __init__(self, network, parameters):
        self._net = network
        self._p = parameters
        self._DYSTOPIC_GUARDS = self._UTOPIC_GUARDS = None
        self._PRIMARY_DYS = []
        self._PRIMARY_U = []

    def initialize(self):
        self.updateGuardLists()

    def nodeSeemsDystopic(node):
        return node.getPort() in [80, 443]

    def updateGuardLists(self):
        """Called at start and when a new consensus should be made & received:
           updates *TOPIC_GUARDS."""
        self._DYSTOPIC_GUARDS = []
        self._UTOPIC_GUARDS = []

        # XXXX not sure what happens if a node changes its ORPort

        for node in self._net.new_consensus():
            if self.nodeSeemsDystopic(node):
                self._DYSTOPIC_GUARDS.add(node)
            else:
                # XXXX Having this be 'else' means that FirewallPorts
                # XXXX has affect even when FascistFirewall is disabled.
                # XXXX Interesting!  And maybe bad!
                self._UTOPIC_GUARDS.add(node)

    def getPrimaryList(self, dystopic):
        if dystopic:
            return self._PRIMARY_DYS
        else:
            return self._PRIMARY_U

    def getFullList(self, dystopic):
        if dystopic:
            return self._DYSTOPIC_GUARDS
        else:
            return self._UTOPIC_GUARDS

    def getNPrimary(self, dystopic):
        return self._p.PRIMARY_GUARDS

    def addGuard(self, node, dystopic=False):
        lst = self.getPrimaryList(dystopic)
        lst.append(Guard(node))

        # prop241: if we have added too many guards too recently, die!
        # XXXX Is this what prop241 actually says?
        nRecent = 0
        for g in lst:
            if g.addedWithin(self._p.TOO_RECENTLY):
                nRecent += 1
        if nRecent >= self._p.TOO_MANY_GUARDS:
            raise GivingUp("Too many guards added too recently!")

    def inADystopia(self):
        return False # XXXXX

    def netLooksDown(self):
        return False # XXXXX

    def nodeIsInGuardList(self, n, gl):
        for g in gl:
            if g.getNode() == n:
                return True
        return False

    def getGuard(self):
        """We're about to build a circuit: returns a guard to try."""
        dystopic = self.inADystopia()
        lst = self.getPrimaryList(dystopic)

        usable = [ g for g in lst if g.canTry() ]

        if len(usable):
            # But we just use the first one
            return usable[0]

        if len(lst) >= self.getNPrimary(dystopic):
            # Can't add any more!

            # Can't 
            
            for g in lst:
                g.markForRetry()

        full = self.getFullList(dystopic)
        possible = [ n for n in full if not self.nodeIsInGuardList(n, lst) ]
        newnode = random.choice(possible)
        self.addGuard(newnode, dystopic)
        newguard = lst[-1]
        assert newguard.getNode() == newnoce

        return newguard

    def connectToGuard(self, guard):
        up = self._net.probe_node_is_up(guard.getNode())
        guard.mark(up)
        return up

    def buildCircuit(self):
        if self.netLooksDown():
            return False
        g = self.getGuard()
        return self.connectToGuard(g)
