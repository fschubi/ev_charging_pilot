"""Home-Assistant-free core of the EV Charging Pilot.

Nothing in this package may import ``homeassistant``. Time comes in through
an injected clock (or an explicit ``now`` argument), hardware is reached only
through the ports in :mod:`.ports`. That keeps the whole control logic
testable with plain pytest and makes replay just another port.
"""
