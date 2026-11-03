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

**Door**:
A doorway drawn on a vector plan, joining two rooms, or a room and somewhere that is no
room (a landing, a stair hall, the street). Known by its drawn swing arc and by nothing
else: two arcs meeting in one doorway are one double door, a sliding door or a bare opening
is not a door, and an arc swinging onto a **placard** is the placard's door, not a door.
A picture plan has no doors read. A door belongs to neither room it joins.
_Avoid_: opening, baie, passage, door arc

**Door role**:
Which width a **door** is held to, read from its two sides: two rooms make an *interior
door*; a room and no room make the *entrance door*; no room on either side is a door of the
communs, shown but not checked. A guess until the sheet is split into homes, so the verdict
always says which role it assumed.
_Avoid_: door type, door kind

### Checks

**Door width**:
A **door**'s nominal width, read as the radius of its swing arc (the wider leaf for a
double door), as architects draw it. Doors are catalogue sizes, so a radius within 3 cm of
0.60, 0.70, 0.80, 0.90 or 1.00 m is read as that size; the measured radius is always shown
beside it. An interior door needs 0.80 m, the entrance door 0.90 m. The passage utile is
never drawn on a plan, so it is never judged.
_Avoid_: opening width, passage utile, clear width

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

**Walk**:
Which rooms a wheelchair reaches from a start, through **doors** wide enough, and where it
stops. It starts outside, through the entrance door, or in a hall when there is none; the
auditor may start it from any room, which is only where they look from, never a
**correction**. A narrow door is a **stop** it does not pass; a room where the turning
circle fails is a stop it still rolls through. Played as one continuous route, depth first,
backing out the way it came.
_Avoid_: path, journey, navigation, route (for the verdict)

**Stop**:
A place the **walk** shows in red: a door too narrow to pass, or a reached room where the
wheelchair cannot turn around.
_Avoid_: blocker, failure, obstacle

**Accessible WC**:
A WC or bathroom whose **toilet** has a **transfer space**. A home needs at least one; the
other toilets are shown but do not decide the home's verdict.
_Avoid_: PMR WC, adapted toilet

**Explanation**:
Why a check failed, in plain language, and the smallest change on the plan that would
make it pass. Written from the measured numbers by Muse Spark, or from a template when
no model answers. It never changes the verdict: the geometry decides, the explanation
only speaks.
_Avoid_: justification, rationale, AI verdict

**Doubtful**:
A failure the verifier (Muse Spark Open on Baseten) disagrees with, or agrees with too
weakly to trust. Shown to the auditor as a flag on the explanation; the verdict itself
still stands until a **correction** changes how the plan was read.
_Avoid_: uncertain, suspicious, low-confidence verdict

### Auditing

**Proposal**:
A change to the design tried on paper, such as widening a narrow **door** to the width it
needs, so the **walk** can be played again as if it were built that way. It answers "what
would fix this?", where a **correction** answers "was this read right?". It is never stored
and never changes a verdict: the report still judges the plan as drawn.
_Avoid_: fix (for the action), what-if, simulation

**Correction**:
A change an auditor makes to how a plan was read (merging a nook into a room, drawing a
missing wall, removing a **fixture** or a **door** that is not there), kept with the plan and
replayed each time it is read. A door is never drawn by hand.
_Avoid_: fix, override, edit, annotation
