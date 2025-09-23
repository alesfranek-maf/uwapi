import json
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="UW Prototypes Browser", layout="wide")

@st.cache_data
def load_data(path: str = "prototypes.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # normalise second-level keys to ints if possible
    normalised = {}
    for group, items in data.items():
        try:
            normalised[group] = {int(k): v for k, v in items.items()}
        except Exception:
            normalised[group] = items
    return normalised

data = load_data()
if not data:
    st.error("prototypes.json not found or empty")
    st.stop()

# --- Preprocessing: build id→name map and split Units ---
# Build global id→name map from all groups
id_to_name = {}
for grp, items in data.items():
    for pid, obj in items.items():
        if isinstance(obj, dict):
            n = obj.get("name")
            if isinstance(n, str):
                id_to_name[pid] = n

# Split Unit group into two synthetic groups
if "Unit" in data:
    buildings = {}
    combat = {}
    for pid, obj in data["Unit"].items():
        if isinstance(obj, dict) and (obj.get("buildingRadius") is not None):
            buildings[pid] = obj
        else:
            combat[pid] = obj
    # Remove original Unit and add two derived groups (only if non-empty)
    del data["Unit"]
    if buildings:
        data["Unit - buildings"] = buildings
    if combat:
        data["Unit - combat"] = combat

# Helper to replace any values that look like IDs with "{name} ({id})"
# except when the key is exactly "id".
from typing import Any

def _replace_ids_in_value(val: Any):
    if isinstance(val, int) and val in id_to_name:
        return f"{id_to_name[val]} ({val})"
    if isinstance(val, list):
        return [_replace_ids_in_value(v) for v in val]
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            if k == "id":
                out[k] = v
            else:
                out[k] = _replace_ids_in_value(v)
        return out
    return val

groups = list(data.keys())
selected_group = st.sidebar.radio("Group", groups, index=0)
items = data[selected_group]

# Flatten items to list of dicts with id and name ensured
records = []
for pid, obj in items.items():
    rec = {"id": pid}
    if isinstance(obj, dict):
        rec.update(obj)
    else:
        rec["value"] = obj
    # Replace any integer values that reference known entity IDs with "name (id)"
    # while keeping the primary 'id' field numeric.
    transformed = {}
    for k, v in rec.items():
        if k == "id":
            transformed[k] = v
        else:
            transformed[k] = _replace_ids_in_value(v)
    records.append(transformed)

st.title(f"{selected_group}")

# Build dynamic filters for all attributes
all_keys = sorted({k for r in records for k in r.keys()})
# Always keep id and name first
ordered_keys = [k for k in ["name", "id"] if k in all_keys] + [k for k in all_keys if k not in {"name", "id"}]

with st.sidebar.expander("Filters", expanded=True):
    text_filters = {}
    bool_filters = {}
    num_ranges = {}
    list_includes = {}
    dict_key_includes = {}
    num_domains = {}
    id_selected = None

    ignore_filters = st.checkbox(
        "Ignore all filters (show everything)",
        key=f"{selected_group}:ignore_filters",
        value=False,
    )

    # Precompute simple stats
    def _is_number(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    for key in ordered_keys:
        values = [r.get(key) for r in records if key in r]
        if not values:
            continue
        # Decide widget by predominant type
        non_none = [v for v in values if v is not None]
        if not non_none:
            continue
        sample = non_none[0]
        if isinstance(sample, bool):
            choice = st.selectbox(
                f"{key}",
                ["Any", True, False],
                index=0,
                key=f"{selected_group}:{key}:bool",
            )
            if choice != "Any":
                bool_filters[key] = choice
        elif _is_number(sample):
            nums = [float(v) for v in non_none if _is_number(v)]
            if nums:
                lo, hi = min(nums), max(nums)
                if key == "id":
                    uniq_ids = sorted(set(int(v) for v in non_none if _is_number(v)))
                    id_opt = ["Any"] + [str(uid) for uid in uniq_ids]
                    sel = st.selectbox(
                        "id",
                        id_opt,
                        index=0,
                        key=f"{selected_group}:id:select",
                    )
                    if sel != "Any":
                        id_selected = int(sel)
                else:
                    if lo < hi:
                        num_domains[key] = (float(lo), float(hi))
                        rng = st.slider(
                            f"{key}",
                            min_value=float(lo),
                            max_value=float(hi),
                            value=(float(lo), float(hi)),
                            key=f"{selected_group}:{key}:range",
                            width="stretch"
                        )
                        num_ranges[key] = rng
                    else:
                        st.caption(f"{key}: {lo}")
        elif isinstance(sample, str):
            uniq = sorted({str(v) for v in non_none})
            if uniq and len(uniq) <= 500:
                sel = st.multiselect(
                    f"{key}",
                    uniq,
                    key=f"{selected_group}:{key}:strvals",
                    width="stretch",
                )
                if sel:
                    text_filters[key] = set(sel)
        elif isinstance(sample, list):
            # collect atomic elements
            elems = []
            for v in non_none:
                if isinstance(v, list):
                    elems.extend(v)
            uniq = sorted({e for e in elems if e is not None})
            if uniq and len(uniq) <= 200:
                sel = st.multiselect(
                    f"{key} has any of",
                    uniq,
                    key=f"{selected_group}:{key}:multi",
                    width="stretch"
                )
                if sel:
                    list_includes[key] = set(sel)
        elif isinstance(sample, dict):
            key_pool = sorted({str(kk) for v in non_none if isinstance(v, dict) for kk in v.keys()})
            if key_pool:
                sel_keys = st.multiselect(
                    f"{key} keys",
                    key_pool,
                    key=f"{selected_group}:{key}:dictkeys",
                    width="stretch",
                )
                if sel_keys:
                    dict_key_includes[key] = set(sel_keys)
        else:
            pass

# Apply filters
if ignore_filters:
    filtered = records
else:
    filtered = records
    # Apply id filter first if set
    if id_selected is not None:
        filtered = [r for r in filtered if r.get("id") == id_selected]
    for k, v in bool_filters.items():
        filtered = [r for r in filtered if r.get(k) is v]
    for k, (sel_lo, sel_hi) in num_ranges.items():
        dom_lo, dom_hi = num_domains.get(k, (sel_lo, sel_hi))
        if (sel_lo, sel_hi) == (dom_lo, dom_hi):
            continue  # full range -> no filtering
        tmp = []
        for r in filtered:
            val = r.get(k)
            if isinstance(val, (int, float)) and sel_lo <= float(val) <= sel_hi:
                tmp.append(r)
        filtered = tmp
    for k, txt in text_filters.items():
        # txt is a set of allowed exact string values; require the attribute to exist
        filtered = [r for r in filtered if (r.get(k) is not None) and (str(r.get(k)) in txt)]

    for k, sel_keys in dict_key_includes.items():
        tmp = []
        for r in filtered:
            d = r.get(k)
            if isinstance(d, dict) and any(str(kk) in sel_keys for kk in d.keys()):
                tmp.append(r)
        filtered = tmp
    for k, sel in list_includes.items():
        filtered = [r for r in filtered if isinstance(r.get(k), list) and any(x in sel for x in r[k])]

# Names list and selection
# Build display names (trimmed) and sort case-insensitively
raw_names = [(r.get("name") or str(r.get("id"))).strip() for r in filtered]
name_list = sorted(raw_names, key=lambda s: s.casefold())
# Map normalised names back to records
name_to_obj = { (r.get("name") or str(r.get("id"))).strip(): r for r in filtered }

st.subheader("Results")
st.write(f"{len(filtered)} match(es)")

# Simple inline list of names above the selector
if name_list:
    st.markdown("**Names:**")
    cols = st.columns(5)
    for i, n in enumerate(name_list):
        cols[i % 5].markdown(f"- {n}")

# Allow selecting multiple entities
selected_names = st.multiselect(
    "Select entities to inspect",
    options=name_list,
    default=[],
    key=f"{selected_group}:names:multiselect",
    width="stretch",
)

# Show table and raw attributes for selected entities
if selected_names:
    chosen = [name_to_obj[n] for n in selected_names]
    # Build union of keys across selected
    cols = sorted({k for r in chosen for k in r.keys()})
    # Render compact table of selected entities with all stats
    data_by_name = {n: {c: rec.get(c) for c in cols} for n, rec in zip(selected_names, chosen)}
    try:
        import pandas as pd
        df = pd.DataFrame.from_dict(data_by_name, orient="columns")
    except Exception:
        df = data_by_name
    st.divider()
    st.subheader("Selected entities – table")
    # Wrap long text values to multiple lines for readability
    import textwrap
    for c in df.columns:
        df[c] = df[c].apply(lambda x: "\n".join(textwrap.wrap(str(x), width=40)) if isinstance(x, str) else x)
    st.dataframe(df, width="stretch", height=800)

    # Raw JSON per entity
    st.subheader("Selected entities – raw attributes")
    for n, r in zip(selected_names, chosen):
        st.markdown(f"**{n}**")
        st.json(r, expanded=True, width="stretch")
