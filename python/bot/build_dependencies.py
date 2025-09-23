import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Iterable

PROTOS_PATH = Path("prototypes.json")
OUTPUT_BUILDINGS = Path("info_buildings.json")
OUTPUT_COMBAT = Path("info_combat.json")
OUTPUT_RESOURCES = Path("info_resource.json")

# --- Load prototypes ---
if not PROTOS_PATH.exists():
    raise SystemExit("prototypes.json not found")

data: Dict[str, Dict[str, Any]] = json.loads(PROTOS_PATH.read_text(encoding="utf-8"))

# Normalise second-level keys to ints where possible
norm: Dict[str, Dict[int, Any]] = {}
for group, items in data.items():
    try:
        norm[group] = {int(k): v for k, v in items.items()}
    except Exception:
        # already numeric keys or unexpected
        norm[group] = {int(k) if isinstance(k, str) and k.isdigit() else k: v for k, v in items.items()}

# Build global id->(name, group) map for pretty refs
id_to_name: Dict[int, Tuple[str, str]] = {}
for grp, items in norm.items():
    for eid, obj in items.items():
        if isinstance(eid, int) and isinstance(obj, dict):
            nm = obj.get("name")
            if isinstance(nm, str):
                id_to_name[eid] = (nm, grp)


# Resolve a top-level group name case-insensitively (e.g. "unit" -> "Unit")
def resolve_group(name: str) -> Optional[str]:
    if name in norm:
        return name
    low = name.lower()
    for k in norm.keys():
        if k.lower() == low:
            return k
    return None


# --- Shared helpers ---
def normalise_int_keys(d: Dict[Any, Any]) -> Dict[int, Any]:
    out: Dict[int, Any] = {}
    for k, v in d.items():
        try:
            ki = int(k)
        except Exception:
            continue
        out[ki] = v
    return out


def to_pretty_inputs(inputs: Dict[int, int]) -> List[Dict[str, Any]]:
    pretty: List[Dict[str, Any]] = []
    for res_id, count in inputs.items():
        res_name = id_to_name.get(res_id, (str(res_id), ""))[0]
        pretty.append({"id": res_id, "name": res_name, "count": int(count)})
    return pretty


# Recipe inputs (normalised) indexed by recipe id
recipe_inputs: Dict[int, Dict[int, int]] = {}
for rid, robj in norm.get(resolve_group("Recipe") or "Recipe", {}).items():
    if not isinstance(robj, dict):
        continue
    rin = robj.get("inputs", {})
    if isinstance(rin, dict):
        rin_norm = normalise_int_keys(rin)
        recipe_inputs[int(rid)] = {k: int(v) for k, v in rin_norm.items()}
    else:
        recipe_inputs[int(rid)] = {}


 # Build info from an entity group and a producer group; supports both `output` and `outputs`.
def build_info_unified(entity_type: str, recipe_type: str) -> Dict[int, Dict[str, Any]]:
    ent_group = resolve_group(entity_type)
    rec_group = resolve_group(recipe_type)
    if ent_group is None or rec_group is None:
        return {}

    # Build producer maps by scanning the producer group and trying both `output` and `outputs`
    produced_by_map: Dict[int, List[int]] = {}
    inputs_candidates: Dict[int, List[Dict[int, int]]] = {}
    producer_inputs_map: Dict[int, Dict[int, int]] = {}

    for pid, pobj in norm.get(rec_group, {}).items():
        if not isinstance(pobj, dict):
            continue
        # Inputs on the producer object
        rin = pobj.get("inputs", {})
        rin_norm: Dict[int, int] = {}
        if isinstance(rin, dict):
            rin_norm = {k: int(v) for k, v in normalise_int_keys(rin).items()}
        # Store producer's inputs by its id
        if rin_norm:
            producer_inputs_map[int(pid)] = rin_norm
        # Outputs: support both a single `output` and a dict `outputs`
        outs_ids: List[int] = []
        single_out = pobj.get("output")
        if isinstance(single_out, int):
            outs_ids.append(single_out)
        outs_dict = pobj.get("outputs")
        if isinstance(outs_dict, dict):
            outs_ids.extend(list(normalise_int_keys(outs_dict).keys()))
        for out_id in outs_ids:
            produced_by_map.setdefault(out_id, []).append(int(pid))
            if rin_norm:
                inputs_candidates.setdefault(out_id, []).append(rin_norm)

    ent_ids = {eid for eid in norm.get(ent_group, {}).keys() if isinstance(eid, int)}
    candidate_ids = sorted(ent_ids.intersection(produced_by_map.keys()))

    # Entity-owned recipes map (if the entity objects list a `recipes` array)
    own_recipes: Dict[int, List[int]] = {}
    for eid, eobj in norm.get(ent_group, {}).items():
        if isinstance(eid, int) and isinstance(eobj, dict):
            recs = eobj.get("recipes")
            if isinstance(recs, list):
                acc: List[int] = []
                for r in recs:
                    try:
                        acc.append(int(r))
                    except Exception:
                        continue
                if acc:
                    own_recipes[eid] = acc

    out: Dict[int, Dict[str, Any]] = {}
    for eid in candidate_ids:
        name = get_name(eid)
        node = {"name": name}
        requirements_entries: List[Dict[str, Any]] = []
        producer_ids = produced_by_map.get(eid, []) or []
        for rid in sorted(set(int(r) for r in producer_ids)):
            r_name = get_name(rid)
            r_inputs = producer_inputs_map.get(rid)
            if r_inputs is None:
                r_inputs = recipe_inputs.get(rid, {})
            # Attempt to fetch placeOver from the recipe object, if present
            place_over = None
            recipe_obj = None
            if rec_group in norm and rid in norm[rec_group]:
                recipe_obj = norm[rec_group][rid]
                if isinstance(recipe_obj, dict):
                    place_over = recipe_obj.get("placeOver")
                    if not isinstance(place_over, int):
                        place_over = None
            entry = {
                "id": rid,
                "name": r_name,
                "inputs": to_pretty_inputs(r_inputs),
            }
            if place_over is not None:
                entry["placeOver"] = place_over
            requirements_entries.append(entry)
        node["requirements"] = requirements_entries
        # If the entity itself lists `recipes`, expose them as a simple id+name list
        if eid in own_recipes:
            node["recipes"] = [
                {"id": rr, "name": get_name(rr)} for rr in sorted(set(own_recipes[eid]))
            ]
        out[eid] = node
    return out


def get_name(eid: int) -> str:
    return id_to_name.get(eid, (str(eid), ""))[0]


# --- Build infos using only (entity_type, recipe_type) ---
BUILDINGS_INFO = build_info_unified("Unit", "Construction")
COMBAT_INFO = build_info_unified("Unit", "Recipe")
RESOURCES_INFO = build_info_unified("Resource", "Recipe")

# Write outputs (overwrite each run)
OUTPUT_BUILDINGS.write_text(json.dumps(BUILDINGS_INFO, indent=2), encoding="utf-8")
OUTPUT_COMBAT.write_text(json.dumps(COMBAT_INFO, indent=2), encoding="utf-8")
OUTPUT_RESOURCES.write_text(json.dumps(RESOURCES_INFO, indent=2), encoding="utf-8")
print(f"Wrote {len(BUILDINGS_INFO)} buildings to {OUTPUT_BUILDINGS}")
print(f"Wrote {len(COMBAT_INFO)} combat units to {OUTPUT_COMBAT}")
print(f"Wrote {len(RESOURCES_INFO)} resources to {OUTPUT_RESOURCES}")
