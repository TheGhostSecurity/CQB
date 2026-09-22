"""Headless authoritative geometry probe for assets/m4a1.bam.
Uses walker-based counting + bounding-sphere extent - no fragile pattern
matching. If extent > 0 and geom_nodes > 0 the model is renderable.
"""
from pathlib import Path

from panda3d.core import Filename, Loader, NodePath, load_prc_file_data

load_prc_file_data("", "notify-level warning")

path = Path(__file__).resolve().parent / "assets" / "m4a1.bam"
if not path.exists():
    print("RESULT: FAIL no_bam", path)
    raise SystemExit(2)

node = Loader.get_global_ptr().load_sync(Filename.from_os_specific(str(path)))
if node is None:
    print("RESULT: FAIL load_null")
    raise SystemExit(2)

np = NodePath(node)

geom_nodes = 0
from panda3d.core import GeomNode

stack = [np.node()]
while stack:
    cur = stack.pop()
    if cur.is_of_type(GeomNode.getClassType()):
        geom_nodes += 1
    for child in range(cur.get_num_children()):
        stack.append(cur.get_child(child))

rs = np.get_bounds()
mn = rs.get_min()
mx = rs.get_max()
extent = (mx - mn).length()

print("RESULT:", "OK" if geom_nodes > 0 and extent > 0 else "FAIL_empty")
print("geom_nodes:", geom_nodes)
print("extent:", round(float(extent), 3))
print("min:", tuple(round(float(x), 2) for x in (mn[0], mn[1], mn[2])))
print("max:", tuple(round(float(x), 2) for x in (mx[0], mx[1], mx[2])))
