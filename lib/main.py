
from py3hax import *
import tornet
import simtime
import client


def trivialSimulation():
    net = tornet.Network(100)

    # Decorate the network.
    # Uncomment one or two of these at a time, kthx!
    #net = tornet.FascistNetwork(net)
    #net = tornet.FlakyNetwork(net)
    #net = tornet.EvilFilteringNetwork(net)
    #net = tornet.SniperNetwork(net)

    c = client.Client(net, client.ClientParams())

    ok = 0
    bad = 0

    for period in xrange(30): # one hour each
        for subperiod in xrange(30): # two minutes each
            if (subperiod % 10) == 0:
                # nodes left and arrived
                net.do_churn()
            # nodes went up and down
            net.updateRunning()

            for attempts in xrange(6): # 20 sec each

                # actually have the client act.
                if c.buildCircuit():
                    ok += 1
                else:
                    bad += 1

                # time passed
                simtime.advanceTime(20)

        # new consensus
        c.updateGuardLists()

    print(ok, (ok+bad))
    print(ok / float(ok+bad))

if __name__ == '__main__':
    trivialSimulation()
