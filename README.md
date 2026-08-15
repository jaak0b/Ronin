# Ronin

A high-performance, center-of-mass-optimized CNC toolchanger mod for the Monolith gantry.

Ronin swaps pre-heated hotend modules mid-print for multi-material and multi-color printing. The swap needs no extra motors: printhead XY motion does the docking and undocking, and the hotend module is held on the printhead by a magnetic kinematic coupling. Metal where stiffness matters (CNC aluminum backplate, SLM aluminum hotend mount), printed parts where it does not.

## Origins

Ronin started as a mod of [CxChanger](https://github.com/cx330-TXY/CxChanger) by cx330-TXY. The core idea — an underactuated hotend swap driven by printhead motion, with a magnetic kinematic coupling on the module — comes from there and still defines how Ronin works.

Over time the design drifted far enough that nothing interchanges with the original anymore: coupling layout, magnet arrangement, backplate, hotend mount and the extruder placement are all new. At that point keeping the CxChanger name would have implied a compatibility that no longer exists, so it got a new one.

## Thanks

Huge thanks to **zruncho** ([madmax](https://github.com/zruncho3d/madmax)) for the help along the way. Without his input on the coupling, the magnet layout and many other details the design would look totally different today.

## The design

<!-- CAD render goes here -->
![Ronin toolhead CAD](docs/images/ronin-cad.png)

## Status

Work in progress. Parts are being ordered and tested; expect things to change. Nothing here should be considered final until this note goes away.
