#!/usr/bin/python

"""
   Let's simulate a tor network!  We're only going to do enough here
   to try out guard selection/replacement algorithms from proposal
   259, and some of its likely variants.
"""

import math
import random

class Node:
    def __init__(self, name, port, evil=False, reliability=0.999):
        self._name = name
        self._port = port
        self._evil = evil
        self._reliabilitiy = 0.999
        self._up = True
        self._dead = False

    def updateRunning(self):
        if not self._dead:
            self._up = random.random() < self._reliability

    def kill(self):
        self._dead = True
        self._up = False

    def resurrect(self):
        self._dead = False
        self.updateRunning()

    def getPort(self):
        return self._port

    def isReallyUp(self):
        return self._up

    def isReallyEvil(self):

def _randport(pfascistfriendly):
    if random.random() < pfascistfriendly:
        return random.choice([80, 443])
    else:
        return random.randint(1,65535)

class Network:
    def __init__(self, num_nodes, pfascistfriendly=.3, pevil=0.5,
                 avgnew=2.5, avgdel=2):
        self._wholenet = [ Node("node%d"%n,
                                port=_randport(pfascistfriendly),
                                evil=random.random() < pevil)
                           for n in xrange(num_nodes) ]
        for node in self._wholenet:
            node.updateRunning()

        self._lamdbaAdd = 1.0 / avgnew
        self._lamdbaDel = 1.0 / avgdel
        self._total = n

    def new_consensus(self):
        """Return a list of the running guard nodes."""
        return [ node for node in self._wholenet if node.isReallyUp() ]

    def do_churn(self):
        nAdd = int(random.expovariate(self._lamdbaAdd) + 0.5)
        nDel = int(random.expovariate(self._lamdbaDel) + 0.5)

        random.shuffle(self._wholenet)
        for node in self._wholenet[:nDel]:
            node.kill()

        for n in xrange(self._total, self._total+nAdd):
            node = Node("node%d"%n,
                        port=_randport(pfascistfriendly),
                        evil=random.random() < pevil)
            self._total += 1

        for node in self._wholenet:
            node.updateRunning()

    def probe_node_is_up(self, node):
        return node.isReallyUp()


class _NetworkDecorator:
    def __init__(self, network):
        self._network = network

    def new_consensus(self):
        return self._network.new_consensus()

    def do_churn(self):
        self._network.do_churn()

    def probe_node_is_up(self, node):
        return self._network.probe_node_is_up(node)

class FascistNetwork(_NetworkDecorator):
    def probe_node_is_up(self, node):
        return node.getPort() in [80,443] and self._network.probe_node_is_up(node)


class EvilFilteringNetwork(_NetworkDecorator):
    def probe_node_is_up(self, node):
        return node.isReallyEvil() and self._network.probe_node_is_up(node)

class EvilKillingNetwork(_NetworkDecorator):
    def probe_node_is_up(self, node):
        result = self._network.probe_node_is_up(node)

        if not node.isReallyEvil():
            node.kill()

        return result

