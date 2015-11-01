Guard simulator for proposals 241, 259, ...
===========================================

This code is the latest hack among many to try to simulate our chosen
guard algorithm.  It's good to play with until we're sure we've got
the rigor that we want!

I've stuck it at https://github.com/nmathewson/guardsim .

lib/tornet.py has a very oversimplified view of "who's a guard and who
isn't", and of various network attackers.

doc/stuff-to-test.txt has a list of potentially interesting scenarios
we should simulate someday.

lib/client.py has an attempt to implement the client guard selection
algorithm.  I *tried* to follow prop259 approximately as I
understood it, but I probably did a lot of stuff wrong.

The code runs, but it's littered with XXXX comments. It could
probably use more logging and a better main-loop.

If you're going to focus on just one thing, I'd suggest making the
client.py code more closely represent proposal 259, and extending
proposal 259 to fill in any gaps that it doesn't describe which you
need in order to make the code behave nicely.

If you're going to focus on another thing, I'd suggest making it
report more things.