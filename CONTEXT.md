# ConformScope

ConformScope reads a home's building plan and checks, with real geometry, whether a
wheelchair user can live there under the French accessibility (PMR) rules.

## Language

### On the plan

**Fixture**:
Something built into the plan that a wheelchair cannot stand on: a **placard**, an
**appliance** or a **toilet**. Furniture (a bed, a table, a sofa) is not a fixture, because
it can be moved.
_Avoid_: object, equipment, obstacle, furniture

**Placard**:
Built-in storage drawn on the plan as a box with crossed diagonals, sometimes lettered "PL".
_Avoid_: armoire, wardrobe, closet, cupboard, rangement

**Appliance**:
A **fixture** that stands on the floor and does a job: an oven, a hob, a lave-vaisselle, a
lave-linge, an évier or a washbasin. It is drawn as a small box carrying its symbol ("F",
four circles, "LV", "LL", a drainer, a basin).
_Avoid_: équipement, électroménager, kitchen block

**Washbasin**:
An **appliance** standing in a bathroom or a WC, and the only appliance with its own PMR
rule.
_Avoid_: lavabo, LV, sink, vasque

**Toilet**:
The **fixture**, a bowl and cistern drawn as one rounded symbol. *WC* is the room type of
the compartment it stands in, and a WC with no toilet drawn in it is still a WC.
_Avoid_: WC (for the fixture), cuvette, pan

### Checks

**Transfer space**:
A free 0.80 × 1.30 m rectangle touching a **toilet**, inside the room the toilet stands in,
where a wheelchair parks to transfer onto it. Walls and **fixtures** may not cross it; a
door swing may.
_Avoid_: espace d'usage, aire de transfert, clearance

**Washbasin space**:
A free 0.80 × 1.30 m rectangle touching the front of a **washbasin**, where a wheelchair
faces it. Walls and **fixtures** may not cross it; a door swing may. The rule's source in
the housing arrêté is still to be confirmed.
_Avoid_: espace d'usage, knee space

**Accessible WC**:
A WC or bathroom whose **toilet** has a **transfer space**. A home needs at least one; the
other toilets are shown but do not decide the home's verdict.
_Avoid_: PMR WC, adapted toilet

### Auditing

**Correction**:
A change an auditor makes to how a plan was read (merging a nook into a room, drawing a
missing wall, removing a **fixture** that is not there), kept with the plan and replayed each
time it is read.
_Avoid_: fix, override, edit, annotation
