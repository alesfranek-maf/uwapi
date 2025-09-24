import random
import time
from uwapi import *
import json
from uwapi.interop import UwPriorityEnum

with open("bot/prototypes.json") as f:
    PROTOTYPES = json.load(f)

RACE_NAME = "technocracy"
MY_FORCE = -1
ATV_PROTO_ID = 3039831041  # Unit "ATV"
IGNORED_IDS = {
    3145327874,  # resource: ore
    3000128952,  # recipe: ore
    3778878457,  # recipe: deep oil
    3356655882,  # recipe: smelting ore
    3709603756,  # construction: excavator
    2867524795,  # unit: excavator
    3360801550,  # unit: smelter
    3226437573,  # construction: smelter
}


def _ignored(x):
    try:
        return int(x) in IGNORED_IDS
    except Exception:
        return False


ID_TO_NAME = {}
NAME_TO_ID = {}

for top in ("Upgrade", "Recipe", "Construction", "Resource", "Race", "Unit"):
    for obj in PROTOTYPES.get(top, {}).values():
        _id = obj.get("id")
        _name = obj.get("name")
        if _id is None or _name is None:
            continue
        _id = int(_id)
        # Disambiguate constructions by suffixing their names
        if top == "Construction":
            _name = f"{_name}-construction"
        if top == "Recipe":
            _name = f"{_name}-recipe"
        ID_TO_NAME[_id] = _name
        if _name not in NAME_TO_ID:
            NAME_TO_ID[_name] = _id


# --- Helper functions for force resolution and entity iteration ---
def _force(force):
    return uw_world.my_force_id() if force in (None, -1) else int(force)


def _own_entities(force=None):
    f = _force(force)
    for e in uw_world.entities().values():
        if e.Owner is not None and e.Owner.force == f and e.Proto is not None:
            yield e


def get_race_id():
    for race_id, race_data in PROTOTYPES["Race"].items():
        if race_data["name"] == RACE_NAME:
            return race_data["id"]
    return None


RACE = get_race_id()


def get_static_buildings(my_race=True):
    race_data = PROTOTYPES["Race"].get(str(RACE))
    constructions = PROTOTYPES["Construction"]

    if my_race and race_data:
        construction_ids = set(race_data["constructions"])
    else:
        construction_ids = set(constructions.keys())

    units = PROTOTYPES["Unit"]
    res = {}
    for c_id in construction_ids:
        if _ignored(c_id):
            continue
        c = constructions.get(str(c_id))
        if not c or _ignored(c.get("output")):
            continue
        output_id = str(c["output"])
        unit = units.get(output_id)
        if unit:
            res[unit["id"]] = unit
    return res


def _coerce_int(x):
    if x is None:
        return None
    try:
        return int(x)
    except Exception:
        pass
    if hasattr(x, 'to_int'):
        try:
            return int(x.to_int())
        except Exception:
            pass
    if hasattr(x, 'id'):
        try:
            return int(x.id)
        except Exception:
            pass
    if hasattr(x, 'proto'):
        try:
            return int(x.proto)
        except Exception:
            pass
    return None


def id2name(_id):
    _iid = _coerce_int(_id)
    return ID_TO_NAME.get(_iid) if _iid is not None else None


def ids2names(ids_):
    out = {}
    for i in ids_:
        _iid = _coerce_int(i)
        out[i if _iid is None else _iid] = ID_TO_NAME.get(_iid) if _iid is not None else None
    return out
def recipe_id_of(entity) -> int | None:
    rc = getattr(entity, 'Recipe', None)
    if rc is None:
        return None
    for attr in ('recipe', 'proto', 'id'):
        if hasattr(rc, attr):
            try:
                return int(getattr(rc, attr))
            except Exception:
                pass
    # Fall back to conversion
    rid = _coerce_int(rc)
    return rid


def name2id(name):
    return NAME_TO_ID.get(name)


def names2ids(names):
    return {n: name2id(n) for n in names}


def get_static_combat(my_race=True):
    units = PROTOTYPES["Unit"]
    recipes = PROTOTYPES["Recipe"]

    if my_race:
        buildings = get_static_buildings(my_race=True)
        recipe_ids = set()
        for b in buildings.values():
            for rid in b.get("recipes", []):
                if _ignored(rid):
                    continue
                recipe_ids.add(int(rid))
    else:
        recipe_ids = {int(k) for k in recipes.keys() if not _ignored(k)}

    res = {}
    for rid in recipe_ids:
        if _ignored(rid):
            continue
        r = recipes.get(str(rid))
        if not r:
            continue
        for out_id in r.get("outputs", {}).keys():
            try:
                uid = int(out_id)
            except Exception:
                continue
            if _ignored(uid) or uid == ATV_PROTO_ID:
                continue
            u = units.get(str(uid))
            if u:
                res[u["id"]] = u
    return res


def get_static_resources(my_race=True):
    resources = PROTOTYPES["Resource"]
    recipes = PROTOTYPES["Recipe"]
    if my_race:
        buildings = get_static_buildings(my_race=True)
        recipe_ids = set()
        for b in buildings.values():
            for rid in b.get("recipes", []):
                if _ignored(rid):
                    continue
                recipe_ids.add(int(rid))
    else:
        recipe_ids = {int(k) for k in recipes.keys() if not _ignored(k)}
    res = {}
    for rid in recipe_ids:
        if _ignored(rid):
            continue
        r = recipes.get(str(rid))
        if not r:
            continue
        for out_id in r.get("outputs", {}).keys():
            try:
                oid = int(out_id)
            except Exception:
                continue
            if _ignored(oid):
                continue
            rr = resources.get(str(oid))
            if rr:
                res[rr["id"]] = rr
    return res


STATIC_BUILDINGS = get_static_buildings(True)
STATIC_RESOURCES = get_static_resources(True)
STATIC_COMBAT = get_static_combat(True)
ALL_STATIC_BUILDINGS = get_static_buildings(False)
ALL_STATIC_RESOURCES = get_static_resources(False)
ALL_STATIC_COMBAT = get_static_combat(False)


def get_recipes_for_combat(combat_id, my_race=True):
    if _ignored(combat_id):
        return None
    recipes = PROTOTYPES["Recipe"]
    if my_race:
        allowed = {int(rid) for b in get_static_buildings(my_race=True).values() for rid in b.get("recipes", []) if
                   not _ignored(rid)}
    else:
        allowed = {int(k) for k in recipes.keys() if not _ignored(k)}
    cid = str(int(combat_id))
    for rid in allowed:
        if _ignored(rid):
            continue
        r = recipes.get(str(rid))
        if r and cid in r.get("outputs", {}):
            return r
    return None


def get_buildings_for_recipe(recipe_id, my_race=True):
    if _ignored(recipe_id):
        return None
    units = PROTOTYPES["Unit"]
    rid = int(recipe_id)
    search_units = get_static_buildings(my_race=my_race).values() if my_race else units.values()
    for u in search_units:
        if _ignored(u.get("id")):
            continue
        if any(int(r) == rid for r in u.get("recipes", [])):
            return u
    return None


def get_building_inputs(building_id):
    if _ignored(building_id):
        return {}
    cons = PROTOTYPES["Construction"]
    bid = int(building_id)
    for c in cons.values():
        try:
            if _ignored(c.get("id")):
                continue
            if int(c.get("output")) == bid:
                return c.get("inputs", {})
        except Exception:
            continue
    return {}


def get_building_for_combat(combat_id, my_race=True):
    r = get_recipes_for_combat(combat_id, my_race=my_race)
    if not r:
        return None
    return get_buildings_for_recipe(r.get("id"), my_race=my_race)


def get_recipe_for_resource(resource_id, my_race=True):
    if _ignored(resource_id):
        return None
    recipes = PROTOTYPES["Recipe"]
    if my_race:
        allowed = {int(rid) for b in get_static_buildings(my_race=True).values() for rid in b.get("recipes", []) if
                   not _ignored(rid)}
    else:
        allowed = {int(k) for k in recipes.keys() if not _ignored(k)}
    rid_str = str(int(resource_id))
    for rid in allowed:
        if _ignored(rid):
            continue
        r = recipes.get(str(rid))
        if r and rid_str in r.get("outputs", {}):
            return r
    return None


def get_resource_producers(resource_id, my_race=True):
    r = get_recipe_for_resource(resource_id, my_race=my_race)
    if not r:
        return {}
    b = get_buildings_for_recipe(r.get("id"), my_race=my_race)
    return {b["id"]: b} if b else {}


def get_construction_cost(building_id):
    return get_building_inputs(building_id)


def scale_cost(cost_dict, factor):
    return {int(k): v * factor for k, v in ((int(x), y) for x, y in cost_dict.items())}


def merge_costs(*dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            k = int(k)
            out[k] = out.get(k, 0) + v
    return out


def get_combat_cost(combat_id, qty=1, my_race=True):
    r = get_recipes_for_combat(combat_id, my_race=my_race)
    if not r:
        return {}
    return scale_cost(r.get("inputs", {}), qty)


def get_build_plan_for_combat(combat_id, qty=1, my_race=True):
    combat_id = int(combat_id)
    b = get_building_for_combat(combat_id, my_race=my_race)
    r = get_recipes_for_combat(combat_id, my_race=my_race)
    if not r or not b:
        return {"combat_id": combat_id, "combat_name": id2name(combat_id), "error": "missing_building_or_recipe"}
    building_cost = get_construction_cost(b["id"]) or {}
    unit_cost = get_combat_cost(combat_id, qty=qty, my_race=my_race)
    total_cost = merge_costs(scale_cost(building_cost, 1), unit_cost)
    producers = {}
    for rid in total_cost.keys():
        prod = get_resource_producers(rid, my_race=my_race)
        if prod:
            producers[rid] = list(prod.keys())[0]
    return {
        "combat_id": combat_id,
        "combat_name": id2name(combat_id),
        "building_id": b["id"],
        "building_name": b.get("name"),
        "recipe_id": r.get("id"),
        "recipe_name": r.get("name"),
        "building_cost": {int(k): v for k, v in building_cost.items()},
        "combat_cost": {int(k): v for k, v in unit_cost.items()},
        "total_cost": total_cost,
        "producers": producers,
    }


def print_build_plan_for_combat(combat_id, qty=1, my_race=True):
    plan = get_build_plan_for_combat(combat_id, qty=qty, my_race=my_race)
    if plan.get("error"):
        print(f"No plan: {plan['error']} for {combat_id} ({id2name(combat_id) or '?'})")
        return
    print(f"Combat {plan['combat_id']}: {plan['combat_name']}")
    print(f"  Building: {plan['building_id']} ({plan['building_name']})")
    print(f"  Recipe: {plan['recipe_id']} ({plan['recipe_name']})")
    if plan['building_cost']:
        print("  Build cost:")
        for rid, q in plan['building_cost'].items():
            print(f"    - {rid} ({id2name(rid) or '?'}) x{q}")
    if plan['combat_cost']:
        print("  Unit cost:")
        for rid, q in plan['combat_cost'].items():
            print(f"    - {rid} ({id2name(rid) or '?'}) x{q}")
    if plan['total_cost']:
        print("  Total cost:")
        for rid, q in plan['total_cost'].items():
            prod = plan['producers'].get(rid)
            prod_s = f" -> produced by {prod} ({id2name(prod)})" if prod else ""
            print(f"    - {rid} ({id2name(rid) or '?'}) x{q}{prod_s}")


def get_full_plan_recursive(combat_id, qty=1, my_race=True):
    combat_id = int(combat_id)
    buildings_recipes = set()  # set of (building_id, recipe_id)
    base_resources = {}
    visited_buildings = set()

    def add_building(bid, rid=None):
        bid = int(bid)
        if rid is not None:
            buildings_recipes.add((bid, int(rid)))
        if bid in visited_buildings:
            return
        visited_buildings.add(bid)
        for rid_inp, q in get_construction_cost(bid).items():
            _expand_resource(int(rid_inp), int(q), set())

    def add_base_resource(rid, q):
        rid = int(rid)
        base_resources[rid] = base_resources.get(rid, 0) + int(q)

    def _expand_resource(rid, q, path):
        rid = int(rid)
        if q <= 0:
            return
        if rid in path:
            add_base_resource(rid, q)
            return
        r = get_recipe_for_resource(rid, my_race=my_race)
        if not r:
            add_base_resource(rid, q)
            return
        b = get_buildings_for_recipe(r.get("id"), my_race=my_race)
        if not b:
            add_base_resource(rid, q)
            return
        add_building(b["id"], r.get("id"))
        inputs = r.get("inputs", {})
        new_path = set(path)
        new_path.add(rid)
        for in_id, in_qty in inputs.items():
            _expand_resource(int(in_id), int(in_qty) * q, new_path)

    root_building = get_building_for_combat(combat_id, my_race=my_race)
    unit_recipe = get_recipes_for_combat(combat_id, my_race=my_race)
    if root_building:
        add_building(root_building["id"], unit_recipe.get("id") if unit_recipe else None)
    if unit_recipe:
        for rid, q in unit_recipe.get("inputs", {}).items():
            _expand_resource(int(rid), int(q) * int(qty), set())

    return {
        "combat_id": combat_id,
        "combat_name": id2name(combat_id),
        "root_building_id": root_building["id"] if root_building else None,
        "root_building_name": root_building.get("name") if root_building else None,
        "buildings": sorted(list(buildings_recipes)),  # list of (building_id, recipe_id)
        "base_resources": base_resources,
    }


def print_full_plan_recursive(combat_id, qty=1, my_race=True):
    plan = get_full_plan_recursive(combat_id, qty=qty, my_race=my_race)
    print(f"Combat {plan['combat_id']}: {plan['combat_name']}")
    if plan['root_building_id']:
        print(f"  Root building: {plan['root_building_id']} ({id2name(plan['root_building_id'])})")
    if plan['buildings']:
        print("  Buildings to construct (with recipes):")
        for bid, rid in plan['buildings']:
            bname = id2name(bid) or '?'
            rname = id2name(rid) or '?'
            print(f"    - {bid}: {bname}  via  {rid}: {rname}")
    if plan['base_resources']:
        print("  Base resources required:")
        for rid, q in sorted(plan['base_resources'].items()):
            print(f"    - {rid}: {id2name(rid)} x{q}")


def get_build_plan_for_unit_name(unit_name: str, qty=1):
    uid = name2id(unit_name)
    print(f"get_build_plan_for_unit_name: unit_name='{unit_name}' -> uid={uid}")
    if uid is None:
        print(f"get_build_plan_for_unit_name: ERROR unknown unit '{unit_name}'")
        return {"error": f"unknown_unit_name:{unit_name}"}
    plan = get_full_plan_recursive(int(uid), qty=qty)
    print(
        f"get_build_plan_for_unit_name: plan buildings={len(plan.get('buildings', []))} base_resources={len(plan.get('base_resources', {}))}")
    return plan


def _construction_for_building(building_proto_id: int) -> int:
    """Find the construction prototype that outputs the given building prototype. Returns 0 if not found."""
    bid = int(building_proto_id)
    for c in PROTOTYPES["Construction"].values():
        try:
            if int(c.get("output", 0)) == bid:
                return int(c.get("id"))
        except Exception:
            continue
    return 0


def execute_build_plan(plan: dict, *, near_base=None, limit_per_building: int = 1) -> dict:
    """Execute a plan created by get_full_plan_recursive / get_build_plan_for_unit_name.
    - Places constructions for each required building (respecting limit_per_building per type).
    - Sets the specified recipe on any matching built building lacking a recipe.
    Returns a summary dict with placements and any errors.
    """
    if not plan or plan.get("error"):
        err = plan.get("error") if plan else "empty_plan"
        print(f"execute_build_plan: ERROR {err}")
        return {"placed": [], "recipes_set": [], "errors": [err]}

    base = near_base
    if base is None:
        bases = get_buildings_by_name("control core")
        base = next(iter(bases.values()), None)
        print(f"execute_build_plan: resolved base by name -> {base.id if base else None}")
        if base is None:
            base = next((e for e in uw_world.entities().values() if e.own() and e.Unit), None)
            print(f"execute_build_plan: fallback base -> {base.id if base else None}")
    if base is None:
        print("execute_build_plan: ERROR no_base_entity_found")
        return {"placed": [], "recipes_set": [], "errors": ["no_base_entity_found"]}

    placed, recipes_set, errors = [], [], []

    buildings = plan.get("buildings", [])
    print(f"execute_build_plan: processing {len(buildings)} buildings from plan")
    for bid, rid in buildings:
        print(f"execute_build_plan: step building={bid}({id2name(bid)}) recipe={rid}({id2name(rid) if rid else None})")
        cpid = _construction_for_building(int(bid))
        if cpid == 0:
            msg = f"no_construction_for_building:{bid}"
            print(f"execute_build_plan: ERROR {msg}")
            errors.append(msg)
            continue
        pos = building_ask(cpid, base.id, recipe_proto=int(rid) if rid else 0, limit=limit_per_building)
        if pos:
            placed.append({"construction_proto": cpid, "near": base.id, "pos": pos})
        if rid:
            try:
                eid = set_recipe_on_any(int(rid), force=MY_FORCE)
            except Exception as ex:
                print(f"execute_build_plan: set_recipe_on_any(force) failed: {ex}; retrying without force")
                eid = set_recipe_on_any(int(rid))
            if eid:
                recipes_set.append({"entity": eid, "recipe": int(rid)})
                print(f"execute_build_plan: set recipe {rid} on entity {eid}")
            else:
                print(f"execute_build_plan: no eligible entity to set recipe {rid}")

    print(f"execute_build_plan: done placed={len(placed)} recipes_set={len(recipes_set)} errors={len(errors)}")
    return {"placed": placed, "recipes_set": recipes_set, "errors": errors}


def build_unit_by_name(unit_name: str, qty=1, *, near_base=None, my_race=True) -> dict:
    """High level helper: compute plan for the given combat unit name and execute it."""
    plan = get_build_plan_for_unit_name(unit_name, qty=qty, my_race=my_race)
    return execute_build_plan(plan, near_base=near_base)



def _as_int_id(val):
    """Helper to coerce recipe or proto fields to int if possible, handling object wrappers."""
    if val is None:
        return None
    try:
        return int(val)
    except Exception:
        pass
    # Try .to_int() for object wrappers
    if hasattr(val, "to_int"):
        try:
            return int(val.to_int())
        except Exception:
            pass
    return None

def get_buildings(force=None, recipe_proto: int | None = None):
    res = {}
    rid = int(recipe_proto) if recipe_proto is not None else None
    for e in _own_entities(force):
        pid = int(e.Proto.proto)
        if pid in STATIC_BUILDINGS:
            if rid is not None and recipe_id_of(e) != rid:
                continue
            res[e.id] = e
    return res




def get_constructions(force=None, construction_proto: int | None = None, recipe_proto: int | None = None):
    target = int(construction_proto) if construction_proto is not None else None
    rid = int(recipe_proto) if recipe_proto is not None else None
    construction_ids = {int(k) for k in PROTOTYPES["Construction"].keys()}
    res = {}
    for e in _own_entities(force):
        pid = int(e.Proto.proto)
        if pid not in construction_ids:
            continue
        if target is not None and pid != target:
            continue
        if rid is not None and recipe_id_of(e) != rid:
            continue
        res[e.id] = e
    return res


# --- Debugging/inspection helpers for constructions ---
def print_constructions(construction_proto: int | None = None, recipe_proto: int | None = None, *, force=None):
    """Print a table-like list of active constructions and their recipes.
    Optional filters: construction_proto (by proto id) and recipe_proto (by recipe id).
    """
    cons = get_constructions(force=force, construction_proto=construction_proto, recipe_proto=recipe_proto)
    if not cons:
        print("print_constructions: none found")
        return
    print("# constructions (id | proto:name | recipe:name)")
    for eid, e in sorted(cons.items()):
        pid = int(e.Proto.proto)
        rid_int = recipe_id_of(e)
        pname = id2name(pid) or "?"
        rname = id2name(rid_int) if rid_int is not None else "-"
        print(f"  {eid} | {pid}:{pname} | {rid_int or 0}:{rname}")


def print_constructions_by_name(construction_name: str | None = None, recipe_name: str | None = None, *, force=None):
    cpid = name2id(construction_name) if construction_name else None
    rpid = name2id(recipe_name) if recipe_name else None
    return print_constructions(cpid, rpid, force=force)



def get_units(force=None, combat_only=False):
    res = {}
    for e in _own_entities(force):
        if e.Unit is None:
            continue
        if combat_only and int(e.Proto.proto) not in STATIC_COMBAT:
            continue
        res[e.id] = e
    return res


def get_combat(force=None):
    force = uw_world.my_force_id() if force in (None, -1) else int(force)
    return get_units(force=force, combat_only=True)


def get_atv(force=None):
    force = uw_world.my_force_id() if force in (None, -1) else int(force)
    res = {}
    for e in uw_world.entities().values():
        if e.Owner is None or e.Unit is None or e.Proto is None:
            continue
        if e.Owner.force != force:
            continue
        if int(e.Proto.proto) == ATV_PROTO_ID:
            res[e.id] = e
    return res



def get_buildings_by_id(building_proto_id: int, *, recipe_proto: int | None = None, force=None):
    target_id = int(building_proto_id)
    return {eid: e for eid, e in get_buildings(force=force, recipe_proto=recipe_proto).items() if int(e.Proto.proto) == target_id}


def get_buildings_by_name(name: str, *, recipe_proto: int | None = None, force=None):
    bid = name2id(name)
    if bid is None:
        return {}
    return get_buildings_by_id(int(bid), recipe_proto=recipe_proto, force=force)



def buildings_with_recipe(recipe_proto: int, force=None):
    rid = int(recipe_proto)
    res = {}
    for e in _own_entities(force):
        pid = int(e.Proto.proto)
        if pid in STATIC_BUILDINGS and rid in e.proto().data.get("recipes", []):
            res[e.id] = e
    return res



# Helper to validate positions for construction placement
def _is_valid_position(pos) -> bool:
    # In some API versions, a valid position is a non-zero integer handle; in others, it can be a struct.
    # We accept ints > 0, or objects exposing x/y or pos()/to_int().
    if pos is None:
        return False
    if isinstance(pos, (int,)):
        return pos > 0
    # objects: try common attributes
    if hasattr(pos, "x") and hasattr(pos, "y"):
        return True
    if hasattr(pos, "to_int"):
        try:
            return int(pos.to_int()) > 0
        except Exception:
            return False
    if hasattr(pos, "pos"):
        try:
            p2 = pos.pos()
            return _is_valid_position(p2)
        except Exception:
            return False
    return False


def place_construction_near(construction_proto: int, near_entity_id: int, recipe_proto: int = 0,
                            priority: UwPriorityEnum = UwPriorityEnum.Normal):
    base_pos = uw_world.entity(int(near_entity_id)).pos()
    pos = uw_world.find_construction_placement(construction_proto, base_pos, recipe_proto)
    if not _is_valid_position(pos):
        print(f"place_construction_near: no valid placement (proto={construction_proto}, near={near_entity_id}, recipe={recipe_proto}, got={pos} type={type(pos).__name__})")
        return 0
    if isinstance(pos, object) and hasattr(pos, "to_int"):
        try:
            pos_int = int(pos.to_int())
        except Exception:
            pos_int = pos
    else:
        pos_int = pos
    uw_commands.place_construction(construction_proto, pos_int, 0, recipe_proto, priority)
    return pos_int


def building_ask(construction_proto: int, near_entity_id: int, *, recipe_proto: int = 0,
                 priority: UwPriorityEnum = UwPriorityEnum.Normal, limit: int = 1):
    """Attempt to start a construction near an entity when (built with desired recipe) + (under construction with desired recipe) < limit."""
    print(f"building_ask: construction_proto={construction_proto} near_entity_id={near_entity_id} recipe_proto={recipe_proto} limit={limit}")
    c_proto = PROTOTYPES["Construction"].get(str(int(construction_proto)))
    if not c_proto:
        print("building_ask: ERROR unknown construction proto")
        return 0
    building_proto = int(c_proto.get("output", 0))
    # Count buildings of the right proto AND with the desired recipe already set
    finished = [e for e in get_buildings(recipe_proto=int(recipe_proto) if recipe_proto else None).values() if int(e.Proto.proto) == building_proto]
    active = list(get_constructions(construction_proto=int(construction_proto), recipe_proto=int(recipe_proto) if recipe_proto else None).values())
    total = len(finished) + len(active)
    print(f"building_ask: building_proto={building_proto} finished={len(finished)} active={len(active)} total={total}")
    if total >= int(limit):
        print("building_ask: at limit, skipping placement")
        return 0
    pos = place_construction_near(construction_proto, near_entity_id, recipe_proto=recipe_proto, priority=priority)
    if pos:
        print(f"building_ask: placed at pos={pos}")
    else:
        print("building_ask: no valid placement found")
    return pos

def _count_structures_for_construction(construction_proto: int, force=None) -> int:
    force = uw_world.my_force_id() if force in (None, -1) else int(force)
    c_proto = PROTOTYPES["Construction"].get(str(int(construction_proto)))
    if not c_proto:
        return 0
    building_proto = int(c_proto.get("output", 0))
    count = 0
    for e in uw_world.entities().values():
        if e.Owner is None or e.Proto is None:
            continue
        if e.Owner.force != force:
            continue
        p = int(e.Proto.proto)
        if p == building_proto or p == int(construction_proto):
            count += 1
    return count


def set_recipe_on_any(recipe_proto: int, force=MY_FORCE):
    rid = int(recipe_proto)
    for e in buildings_with_recipe(rid, force=force).values():
        if e.Recipe is None:
            uw_commands.set_recipe(e.id, rid)
            return e.id
    return 0


class Bot:
    is_configured: bool = False
    work_step: int = 0  # save some cpu cycles by splitting work over multiple steps

    def __init__(self):
        uw_events.on_update(self.on_update)

    def attack_nearest_enemies(self):
        own_units = [
            x
            for x in uw_world.entities().values()
            if x.own() and x.Unit is not None and x.proto().data.get("dps", 0) > 0
        ]
        if not own_units:
            return
        enemy_units = [
            x for x in uw_world.entities().values() if x.enemy() and x.Unit is not None
        ]
        if not enemy_units:
            return
        for own in own_units:
            if len(uw_commands.orders(own.id)) == 0:
                enemy = min(
                    enemy_units,
                    key=lambda x: uw_map.distance_estimate(own.pos(), x.pos()),
                )
                uw_commands.order(own.id, uw_commands.fight_to_entity(enemy.id))

    def assign_random_recipes(self):
        for own in uw_world.entities().values():
            if not own.own() or own.Unit is None or own.Recipe is not None:
                continue
            recipes = own.proto().data.get("recipes", [])
            if recipes:
                recipe = random.choice(recipes)
                uw_commands.set_recipe(own.id, recipe)

    def configure(self):
        # auto start the game if available
        if (
            self.is_configured
            and uw_game.game_state() == GameState.Session
            and uw_world.is_admin()
        ):
            time.sleep(3)  # give the observer enough time to connect
            uw_admin.start_game()
            return
        # is configuring possible?
        if (
            self.is_configured
            or uw_game.game_state() != GameState.Session
            or uw_world.my_player_id() == 0
        ):
            return
        self.is_configured = True
        uw_game.log_info("configuration start")
        uw_game.set_player_name("Ales")
        uw_game.player_join_force(0)  # create new force
        uw_game.set_force_color(1, 0, 0)
        tech_id = int(next(k for k, v in PROTOTYPES["Race"].items() if v["name"] == "technocracy"))
        uw_game.set_force_race(tech_id)
        if uw_world.is_admin():
            # uw_admin.set_map_selection("planets/tetrahedron.uwmap")
            uw_admin.set_map_selection("special/risk.uwmap")
            uw_admin.add_ai()
            uw_admin.set_automatic_suggested_camera_focus(True)
        global MY_FORCE
        MY_FORCE = uw_world.my_force_id()
        print(f"{MY_FORCE=}")
        uw_game.log_info("configuration done")

    def build_buildings(self):
        print("build_buildings: start")
        bases = get_buildings_by_name("control core")
        base = next(iter(bases.values()), None)
        print(f"build_buildings: base -> {base.id if base else None}")
        if not base:
            print("build_buildings: No base found, aborting")
            return
        print_constructions()
        unit = "drone"
        plan = get_build_plan_for_unit_name(unit, qty=1)
        print(
            f"build_buildings: plan for {unit}: buildings={len(plan.get('buildings', []))} base_resources={len(plan.get('base_resources', {}))}")
        result = execute_build_plan(plan, near_base=base)
        print(
            f"build_buildings: result placed={len(result['placed'])} recipes_set={len(result['recipes_set'])} errors={result['errors']}")

    def on_update(self, stepping: bool):
        self.configure()
        if not stepping:
            return
        self.work_step += 1
        match self.work_step % 10:
            # case 1:
            #     self.attack_nearest_enemies()
            # case 5:
            #     self.assign_random_recipes()
            case 0:
                self.build_buildings()

    def run(self):
        uw_game.log_info("bot-py start")
        if not uw_game.try_reconnect():
            uw_game.set_connect_start_gui(True, "--observer 2")
            if not uw_game.connect_environment():
                # automatically select map and start the game from here in the code
                if False:
                    uw_game.connect_new_server(0, "", "--allowUwApiAdmin 1")
                else:
                    uw_game.connect_new_server()
        uw_game.log_info("bot-py done")
