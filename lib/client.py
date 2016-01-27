#!/usr/bin/python
# -*- coding: utf-8; -*-
#
# This is distributed under cc0. See the LICENCE file distributed along with
# this code.

import random

from functools import partial
from math import floor

from py3hax import *
import simtime


class GivingUp(Exception):
    pass


def sortByBandwidth(guard, other):
    """Comparison function for sorting guards by bandwidth."""
    if guard.node.bandwidth < other.node.bandwidth:
        return -1
    elif guard.node.bandwidth == other.node.bandwidth:
        return 0
    elif guard.node.bandwidth > other.node.bandwidth:
        return 1


class ExponentialTimer(object):
    """Implements an exponential timer using simulated time."""

    def __init__(self, initial, multiplier, action, *args, **kwargs):
        """Create a timer that's ready to fire immediately.

        After it first fires, it won't be ready again until **initial** seconds
        have passed.  Each time after that, it will increase the delay by a
        factor of **multiplier**.
        """
        self._initial_delay = initial
        self._multiplier = multiplier

        # This is a callable which should be called when the timer fires.  It
        # should return a bool, and if that is ``False``, then we should
        # reschedule (with exponential delay, of course).  Otherwise, do
        # nothing (because we assume that the scheduled action was successful).
        self.fireAction = partial(action, *args, **kwargs)

        self.reset()

    def reset(self):
        """Reset the timer to the state when it was first created."""
        self._next = 0
        self._cur_delay = self._initial_delay

    def isReady(self):
        """Return true iff the timer is ready to fire now."""
        return self._next <= simtime.now()

    def fire(self):
        """Fire the timer."""
        assert self.isReady()
        self._next = simtime.now() + self._cur_delay
        self._cur_delay *= self._multiplier

        self.fireAction()


class ClientParams(object):
    """Represents the configuration parameters of the client algorithm, as given
    in proposals 259 and 241.
    """
    def __init__(self,
                 TOO_MANY_GUARDS=100, # XXX too high
                 TOO_RECENTLY=86400,
                 RETRY_DELAY=30,
                 RETRY_MULT=2,
                 PROP241=False,
                 PROP259=False):

        # prop241: if we have seen this many guards...
        self.TOO_MANY_GUARDS = TOO_MANY_GUARDS
        # ...within this many simulated seconds, then "freak out".
        self.TOO_RECENTLY = TOO_RECENTLY

        # wait this long after retrying guards the first time
        self.RETRY_DELAY = RETRY_DELAY
        # wait this much longer (factor) after the first time.
        self.RETRY_MULT = RETRY_MULT

        # which proposal to follow when they diverge
        self.PROP241 = PROP241
        self.PROP259 = PROP259

        # use absolute numbers, rather than percentages, when following prop241
        if self.PROP241:
            self.UTOPIC_GUARDS_THRESHOLD = 3
            self.DYSTOPIC_GUARDS_THRESHOLD = 3
        elif self.PROP259:
            # prop259: percentage of guards to keep in a guard list (utopic)
            self.UTOPIC_GUARDS_THRESHOLD = 0.05
            # prop259: percentage of guards to keep in a guard list (dystopic)
            self.DYSTOPIC_GUARDS_THRESHOLD = 0.05
            # [prop259] Percentage of UTOPIC_GUARDS we try before also trying
            # the DYSTOPIC_GUARDS.
            self.UTOPIC_GUARDLIST_FAILOVER_THRESHOLD = 0.75
            # [prop259] Percentage of DYSTOPIC_GUARDS we try before concluding
            # that the network is down.
            self.UTOPIC_GUARDLIST_FAILOVER_THRESHOLD = 1.00

        # From asn's post and prop259.  This should be a consensus parameter.
        # It stores the number of guards in {U,DYS}TOPIC_GUARDLIST which we
        # (strongly) prefer connecting to above all others.  The ones which we
        # prefer connecting to are those at the top of the
        # {U,DYS}TOPIC_GUARDLIST when said guardlist is ordered in terms of the
        # nodes' measured bandwidth as listed in the most recent consensus.
        self.N_PRIMARY_GUARDS = 3


class Guard(object):
    """Represents what a client knows about a guard."""

    def __init__(self, node):
        # tornet.Node instance
        self._node = node

        # True iff we have marked this node as down.
        self._markedDown = False

        # True iff we have marked this node as up.
        self._markedUp = False

        # True iff we've attempted to connect to this node.
        self._tried = False

        # When did we add it (simulated)?
        self._addedAt = simtime.now()

        # True iff the node is listed as a guard in the most recent consensus
        self._listed = True

    def __str__(self):
        return "%s" % self._node._id

    @property
    def node(self):
        """Return the underlying torsim.Node object for this guard."""
        return self._node

    def mark(self, up):
        """Mark this guard as up or down because of a successful/unsuccessful
        connection attempt.
        """
        self._tried = True
        if up:
            self._markedDown = False
            self._markedUp = True
        else:
            self._markedDown = True
            self._markedUp = False

    def markUnlisted(self):
        """Mark this guard as unlisted because it didn't appear in the most
        recent consensus.
        """
        self._listed = False

    def markListed(self):
        """Mark this guard as listed because it did appear in the most recent
        consensus.
        """
        self._listed = True

    def canTry(self):
        """Return true iff we can try to make a connection to this guard."""
        return self._listed and not (self._tried and self._markedDown)

    def isListed(self):
        """Return true iff the guard is listed in the most recent consensus
        we've seen.
        """
        return self._listed

    def markForRetry(self):
        """Mark this guard as untried, so that we'll be willing to try it
        again.
        """
        # XXXX We never call this unless _all_ the guards in group seem
        # XXXX down.  But maybe we should give early guards in a list
        # XXXX a chance again after a while?
        self._tried = False

    def addedWithin(self, nSec):
        """Return ``True`` iff this guard was added within the last **nSec**
        simulated seconds.
        """
        return self._addedAt + nSec >= simtime.now()


class Client(object):
    """A stateful client implementation of the guard selection algorithm."""

    def __init__(self, network, parameters):

        # a torsim.Network object.
        self._net = network

        # a ClientParams object
        self._p = parameters

        # lists of current guards in the consensus from the dystopic and
        # utopic sets.  each guard is represented here as a torsim.Node.
        self._DYSTOPIC_GUARDS = self._UTOPIC_GUARDS = None

        # lists of Guard objects for the dystopic and utopic guards
        # configured on this client.
        self._PRIMARY_DYS = []
        self._PRIMARY_U = []

        self._dystopianNetworkDownRetryTimer = ExponentialTimer(
            parameters.RETRY_DELAY,
            parameters.RETRY_MULT,
            self.retryNetwork,
        )
        self._utopianNetworkDownRetryTimer = ExponentialTimer(
            parameters.RETRY_DELAY,
            parameters.RETRY_MULT,
            self.retryNetwork,
        )

        # Internal state for whether we think we're on a dystopic network
        self._dystopic = False
        self._networkAppearsDown = False

        self.updateGuardLists()

    @property
    def conformsToProp241(self):
        return bool(self._p.PROP241)

    @property
    def conformsToProp259(self):
        return bool(self._p.PROP259)

    @property
    def guardsThreshold(self):
        """Determine our ``{U,DYS}TOPIC_GUARDS_THRESHOLD``.

        If this client :meth:`~Client.conformsToProp241`, then
        ``{U,DYS}TOPIC_GUARDS_THRESHOLD`` is interpreted as an integer
        specifying the maximum number of entry guards which will be attempted.
        Otherwise, when the client :meth:`~Client.conformsToProp259`, then
        ``{U,DYS}TOPIC_GUARDS_THRESHOLD`` is interpreted as an float
        representing the percentage of the total running entry guards from the
        most recent consensus to which the client will attempt to connect, and
        these two numbers are multiplied and then floored to arrive at the
        maximum number of attempted entry guards.

        :rtype: int
        :returns: The maximum number of guards in either the
            ``UTOPIC_GUARDLIST`` or the ``DYSTOPIC_GUARDLIST`` to which this
            :class:`Client` will consider connecting.
        """
        running_guards = len(self._net.new_consensus())

        if self.conformsToProp259:
            if self.inADystopia:
                r = floor(running_guards * self._p.DYSTOPIC_GUARDS_THRESHOLD)
            else:
                r = floor(running_guards * self._p.UTOPIC_GUARDS_THRESHOLD)
        elif self.conformsToProp241:
            if self.inADystopia:
                r = self._p.DYSTOPIC_GUARDS_THRESHOLD
            else:
                r = self._p.DYSTOPIC_GUARDS_THRESHOLD

        return r

    @property
    def inADystopia(self):
        """Returns ``True`` if we think we're on a dystopic network."""
        self.maybeCheckNetwork()
        return self._dystopic

    @inADystopia.setter
    def inADystopia(self, dystopic):
        """Record whether or not we think we're on a dystopic network.

        :param bool dystopic: Should be ``True`` if we think we're on
            a dystopic network, and ``False`` otherwise.
        """
        self._dystopic = bool(dystopic)
        if self._dystopic:
            print("We're in a dystopia...")

    @property
    def inAUtopia(self):
        """Returns ``True`` if we think we're on a *non-dystopic* network."""
        self.maybeCheckNetwork()
        return not self._dystopic

    @inAUtopia.setter
    def inAUtopia(self, utopic):
        """Record whether or not we think we're on a *non-dystopic* network.

        :param bool utopic: Should be ``True`` if we think we're on
            a *non-dystopic* network, and ``False`` otherwise.
        """
        self._dystopic = not bool(utopic)
        if not self._dystopic:
            print("We're in a utopia...")

    @property
    def networkAppearsDown(self):
        """``True`` if we think the network is down. ``False`` otherwise."""
        return self._networkAppearsDown

    @networkAppearsDown.setter
    def networkAppearsDown(self, isDown):
        """Set whether or not we think the `system is down`__.

        .. _: http://www.homestarrunner.com/systemisdown.html
        """
        if isDown:
            print("The network went down...")
        else:
            print("The network came up...")

        # If we're flipping the state from the network being up to it being
        # down, then reschedule a retry timer:
        if not self._networkAppearsDown and bool(isDown):
            self._utopianNetworkDownRetryTimer.reset()
            self._dystopianNetworkDownRetryTimer.reset()

        self._networkAppearsDown = bool(isDown)

    def checkFailoverThreshold(self):
        """From prop259:

        5.a. When the GUARDLIST_FAILOVER_THRESHOLD of the UTOPIC_GUARDLIST has
             been tried (without success), Alice should begin trying steps 1-4
             with entry guards from the DYSTOPIC_GUARDLIST as well.  Further,
             if no nodes from UTOPIC_GUARDLIST work, and it appears that the
             DYSTOPIC_GUARDLIST nodes are accessible, Alice should make a note
             to herself that she is possibly behind a fascist firewall.
        """
        if self.conformsToProp259:
            nTried = len(self.getPrimaryGuards(self.inADystopia))

            if nTried >= self.guardsThreshold:
                print("We've hit the %stopic failover rate! %s" %
                      "u" if not self.inADystopia else "dys")
                if not self.inADystopia:
                    print("Trying dystopic guards!")
                    self.inAUtopia = False
                elif self.inADystopia:
                    print("Marking the network as down!")
                    self.networkAppearsDown = True

                return False
        return True

    def updateGuardLists(self):
        """Called at start and when a new consensus should be made & received:
           updates *TOPIC_GUARDS."""
        self._DYSTOPIC_GUARDS = []
        self._UTOPIC_GUARDS = []

        # XXXX I'm not sure what happens if a node changes its ORPort
        # XXXX or when the client changes its policies.

        # Temporary set of node IDs for the listed nodes.
        liveIDs = set()

        # We get the latest consensus here.
        for node in self._net.new_consensus():
            liveIDs.add(node.getID())
            if node.seemsDystopic():
                self._DYSTOPIC_GUARDS.append(node)
            else:
                # XXXX Having this be 'else' means that FirewallPorts
                # XXXX has affect even when FascistFirewall is disabled.
                # XXXX Interesting!  And maybe bad!
                self._UTOPIC_GUARDS.append(node)

        # Now mark every Guard we have as listed or unlisted.
        for lst in (self._PRIMARY_DYS, self._PRIMARY_U):
            for g in lst:
                if g.node.getID() in self._ALL_GUARDS:
                    g.markListed()
                else:
                    g.markUnlisted()

    def getPrimaryUtopicGuards(self):
        """Get the list of utopic guards which we should prioritise trying."""
        return self._PRIMARY_U

    def getPrimaryDystopicGuards(self):
        """Get the list of dystopic guards which we should prioritise trying."""
        return self._PRIMARY_DYS

    def getPrimaryGuards(self, dystopic):
        """Get the list of primary guards for a given dystopia setting."""
        if dystopic:
            return self.getPrimaryDystopicGuards()
        return self.getPrimaryUtopicGuards()

    def getFullList(self, dystopic):
        """Get the list of possible Nodes from the consensus for a given
           dystopia setting"""
        if dystopic:
            return self._DYSTOPIC_GUARDS
        else:
            return self._UTOPIC_GUARDS

    def getNPrimary(self, dystopic):
        """Return the number of listed primary guards that we'll allow.

        XXXX Primary Guards is a different thing to the *_GUARDS_THRESHOLDs!
        """
        return self.guardsThreshold

    def addGuard(self, node, dystopic=False):
        """Try to add a single Node 'node' to the 'dystopic' guard list."""
        lst = self.getPrimaryGuards(dystopic)

        # prop241: if we have added too many guards too recently, die!
        # XXXX Is this what prop241 actually says?

        nRecent = 1 # this guard will be recent.
        for g in lst:
            if g.addedWithin(self._p.TOO_RECENTLY):
                nRecent += 1

        if nRecent >= self._p.TOO_MANY_GUARDS:
            raise GivingUp("Too many guards added too recently!")

        # now actually add the guard.
        lst.append(Guard(node))

    def nodeIsInGuardList(self, n, gl):
        """Return true iff there is a Guard in 'gl' corresponding to the Node
           'n'."""
        for g in gl:
            if g.node == n:
                return True
        return False

    def retryNetwork(self, *args, **kwargs):
        """Assuming the network was down, retry from step #0."""
        print("The network was down. Retrying...")
        self.networkAppearsDown = False
        # XXXX no detection for if we've left the dystopia
        self.getGuard(self.inADystopia)

    def maybeCheckNetwork(self):
        """In the actual implementation, this functionality should look (in some
        cross-platform manner) to see if we have a network interface available
        which has some plausibly-seeming configured route.
        """
        if self._dystopic:
            if self._dystopianNetworkDownRetryTimer.isReady():
                self._dystopianNetworkDownRetryTimer.fire()
        else:
            if self._utopianNetworkDownRetryTimer.isReady():
                self._utopianNetworkDownRetryTimer.fire()

    def getGuard(self, dystopic):
        """We're about to build a circuit: return a guard to try."""

        if self.conformsToProp259:
            # 0. Determine if the local network is potentially accessible.
            self.maybeCheckNetwork()
            if self.networkAppearsDown:
                # XXXX [prop259] It isn't very well defined what we should do if
                # the network seems to be down…
                print("The network is (still) down...")
                return None

        # 2. [prop259]: If the PRIMARY_GUARDS on our list are marked offline,
        # the algorithm attempts to retry them, to ensure that they were not
        # flagged offline erroneously when the network was down.  This retry
        # attempt happens only once every 20 mins to avoid infinite loops.
        #
        # (This step happens in automatically, because
        # Client.retryPrimaryGuards() is called every twenty minutes on a
        # timer. )

        # This is the underlying list that we modify, AND the list
        # we look at.
        # XXXX are these supposed to be different lists?  Are we
        # XXXX also supposed to consider non-dystopian guards
        # XXXX when we think we're not in a dystopia?
        lst = self.getPrimaryGuards(dystopic)

        usable = [ g for g in lst if g.canTry() ]
        listed = [ g for g in lst if g.isListed() ]

        # See if we should retry or add more or use what we have.
        # Here we consider the number of currently-guardy guards.

        if len(usable) == 0 and len(listed) >= self.getNPrimary(dystopic):
            # We can't add any more and we don't have any to try.

            # XXXX should this be two separate timers, one for each list?
            if self._networkDownRetryTimer.isReady():
                self._networkDownRetryTimer.fire()
                for g in lst:
                    g.markForRetry()

            usable = [ g for g in lst if g.canTry() ]

            if not len(usable):
                return None

        if len(usable):
            # Just use the first one that isn't down.
            assert usable[0] != None
            return usable[0]

        # We can add another one.
        full = self.getFullList(dystopic)
        possible = [ n for n in full if not self.nodeIsInGuardList(n, lst) ]
        if len(possible) == 0:
            return None
        newnode = random.choice(possible)
        self.addGuard(newnode, dystopic)
        newguard = lst[-1]
        assert newguard.node == newnode

        return newguard

    def connectToGuard(self, guard):
        """Try to connect to 'guard' -- if it's up on the network, mark it up.
           Return true on success, false on failure."""
        up = self._net.probe_node_is_up(guard.node)
        guard.mark(up)
        return up

    def buildCircuit(self):
        """Try to build a circuit; return true if we succeeded."""
        self.maybeCheckNetwork()

        if self.networkAppearsDown:
            print("Failing circuit because the network is down.")
            return False

        g = self.getGuard(self.inADystopia)

        if not g:
            return False
        return self.connectToGuard(g)
