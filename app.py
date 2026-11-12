import hashlib
import re
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

# ======================= SETTINGS =======================
CATEGORIES = ["Crystal", "Pod", "Shelper"]   # nayi category yahan add karein
COLS = ["id", "category", "vendor", "size", "color", "cartons",
        "priority", "status", "ordered_on", "received_on"]
NEW = "➕ Naya likhein"
NO_VENDOR = "(vendor nahi likha)"
CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="centered")

st.markdown("""
<style>
/* --- Ultra-Professional Mobile-First Enterprise Styling --- */
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 0.8rem; padding-bottom: 5rem; max-width: 720px;}

/* Clean Modern Typography */
h1 {font-size: 1.3rem !important; font-weight: 700; color: #0f172a; margin-bottom: 0.3rem;}
h3 {font-size: 1.1rem !important; font-weight: 600; color: #1e293b;}
h5 {font-size: 0.9rem !important; font-weight: 600; color: #334155; margin-top: .5rem;}

/* Professional Touch Controls & Buttons */
.stButton > button, .stDownloadButton > button {
    min-height: 2.9rem; border-radius: 10px; font-weight: 600; width: 100%;
    border: 1px solid #cbd5e1; background-color: #ffffff; color: #1e293b;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.stPrimaryButton > button {
    background-color: #0f172a !important; color: #ffffff !important; border: none !important;
}

/* Inputs styling */
[data-baseweb="select"] > div, div[data-baseweb="input"] input {
    border-radius: 10px !important; min-height: 2.8rem !important;
}

/* Cards & Expanders */
[data-testid="stExpander"] details {
    border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03); margin-bottom: 0.4rem;
}
[data-testid="stExpander"] summary {padding: .7rem .9rem; font-weight: 600; color: #1e293b;}

/* Tabs */
button[data-baseweb="tab"] {font-weight: 600; padding: .5rem 1rem; font-size: 0.9rem;}

/* Stat Cards */
.stats {display: flex; gap: 8px; margin: .3rem 0 .9rem;}
.stat {flex: 1; border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc;
       padding: .5rem .3rem; text-align: center;}
.stat .v {font-size: 1.25rem; font-weight: 700; color: #0f172a; line-height: 1.2;}
.stat .l {font-size: 0.65rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em;}
</style>
""", unsafe_allow_html=True)


# ---------- Password ----------
def token():
    return hashlib.sha256(("stock-app::" + st.secrets["APP_PASSWORD"]).encode()).hexdigest()[:40]


def check_password():
    if st.session_state.get("ok"):
        return True
    if st.query_params.get("t") == token():
        st.session_state["ok"] = True
        return True
    st.title("📦 Stock On The Way")
    pw = st.text_input("Password", type="password")
    if pw and pw == st.secrets["APP_PASSWORD"]:
        st.session_state["ok"] = True
        st.query_params["t"] = token()
        st.rerun()
    elif pw:
        st.error("Galat password")
    return False


if not check_password():
    st.stop()


# ---------- Database ----------
@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def load_all():
    rows, start = [], 0
    while True:
        chunk = (db().table("orders").select("*").order("id")
                 .range(start, start + 999).execute().data)
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    df = pd.DataFrame(rows, columns=COLS)
    df["cartons"] = pd.to_numeric(df["cartons"]).fillna(0).astype(int)
    df["priority"] = df["priority"].fillna(False).astype(bool)
    for c in ["category", "vendor", "size", "color"]:
        df[c] = df[c].fillna("").astype(str)
    df["size_num"] = pd.to_numeric(
        df["size"].str.extract(r"(\d+\.?\d*)", expand=False), errors="coerce"
    ).fillna(9999)
    return df


def update_rows(ids, fields):
    db().table("orders").update(fields).in_("id", [int(i) for i in ids]).execute()


# ---------- Draft & Hidden Lists Management ----------
def load_draft():
    base = {
        "vendor": "", "category": CATEGORIES[0], "size": "",
        "lines": [], "new_sizes": [], "new_colors": [],
        "del_vendors": [], "del_sizes": [], "del_colors": []
    }
    try:
        rows = db().table("drafts").select("*").eq("key", "main").execute().data
        if rows and rows[0].get("data"):
            base.update(rows[0]["data"])
        return base, True
    except Exception:
        return base, False


def save_draft():
    try:
        db().table("drafts").upsert({"key": "main", "data": st.session_state["draft"]}).execute()
    except Exception:
        st.session_state["draft_ok"] = False


try:
    alld = load_all()
except Exception as e:
    st.error("Database connection error. Ensure Supabase is active.")
    st.caption(str(e))
    st.stop()

otw = alld[alld["status"] == "on_the_way"]


# ---------- Helpers ----------
def size_key(s):
    m = re.search(r"\d+\.?\d*", s)
    return (float(m.group()) if m else 9999.0, s)


def clean_text(s):
    return " ".join(s.strip().split()).title()


def clean_size(s):
    s = s.strip().lower().replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        s += "mm"
    return s


def canon(val, opts):
    for o in opts:
        if o.lower() == val.lower():
            return o
    return val


def sort_df(d):
    return (d.assign(_k=d["category"].map(CAT_ORDER).fillna(99),
                     _c=d["color"].str.lower(), _v=d["vendor"].str.lower())
            .sort_values(["_k", "size_num", "size", "_c", "_v", "id"])
            .drop(columns=["_k", "_c", "_v"]))


def search(d, q):
    hay = (d["category"] + " " + d["size"] + " " + d["color"] + " " + d["vendor"]).str.lower()
    mask = pd.Series(True, index=d.index)
    for tok in q.lower().split():
        mask &= hay.str.contains(tok, regex=False)
    return d[mask]


def stat_cards(items):
    html = "".join(f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>'
                   for l, v in items)
    st.markdown(f'<div class="stats">{html}</div>', unsafe_allow_html=True)


# ---------- Home list ----------
def render_list(d, manage, kp):
    if d.empty:
        st.info("Koi maal nahi mila.")
        return
    d = sort_df(d)
    for (size, color), g in d.groupby(["size", "color"], sort=False):
        star = " ⭐" if g["priority"].any() else ""
        with st.expander(f"{size} {color}{star} — {int(g['cartons'].sum())} carton"):
            vend = g.assign(vendor=g["vendor"].replace("", NO_VENDOR)) \
                    .groupby("vendor")["cartons"].sum().sort_index(key=lambda x: x.str.lower())
            for v, n in vend.items():
                st.write(f"**{v}**: {int(n)} carton")
            if manage:
                st.divider()
                has_pri = bool(g["priority"].any())
                if st.button("⭐ Priority hatayen" if has_pri else "⭐ Priority lagayen",
                             key=f"{kp}pg{size}_{color}"):
                    update_rows(g["id"].tolist(), {"priority": not has_pri})
                    st.rerun()
                for _, r in g.iterrows():
                    st.write(f"{r['vendor'] or NO_VENDOR}: {r['cartons']} • {r['ordered_on']}")
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Received", key=f"{kp}rcv{r['id']}"):
                        update_rows([r["id"]], {"status": "received",
                                                "received_on": str(date.today())})
                        st.session_state["last_rcv"] = {
                            "ids": [int(r["id"])],
                            "label": f"{size} {color} ({r['vendor'] or NO_VENDOR}: {r['cartons']} carton)"}
                        st.rerun()
                    with c2.popover("✏️ Edit"):
                        nv = st.text_input("Vendor", value=r["vendor"], key=f"{kp}v{r['id']}")
                        nc = st.number_input("Cartons", min_value=1, step=1,
                                             value=max(int(r["cartons"]), 1), key=f"{kp}c{r['id']}")
                        npri = st.checkbox("⭐ Priority", value=bool(r["priority"]),
                                           key=f"{kp}s{r['id']}")
                        if st.button("Save", key=f"{kp}sv{r['id']}"):
                            update_rows([r["id"]], {"vendor": clean_text(nv), "cartons": int(nc),
                                                    "priority": bool(npri)})
                            st.session_state["msg"] = "Updated successfully ✅"
                            st.rerun()
                    st.divider()


# ======================= PAGE =======================
st.title("📦 Stock On The Way")
if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))

if "last_rcv" in st.session_state:
    lr = st.session_state["last_rcv"]
    st.info(f"✅ Received: {lr['label']}")
    u1, u2 = st.columns(2)
    if u1.button("↩️ Undo", key="undo"):
        db().table("orders").update({"status": "on_the_way", "received_on": None}) \
            .in_("id", lr["ids"]).eq("status", "received").execute()
        del st.session_state["last_rcv"]
        st.session_state["msg"] = "Restored to On the way ✅"
        st.rerun()
    if u2.button("✖ Dismiss", key="undo_x"):
        del st.session_state["last_rcv"]
        st.rerun()

tabs = st.tabs(["🏠 Home", "➕ Naya Bill", "📜 History"])

# ---------- HOME ----------
with tabs[0]:
    stat_cards([("Total cartons", int(otw["cartons"].sum())),
                ("Items", otw.groupby(["category", "size", "color"]).ngroups),
                ("⭐ Priority", int(otw.loc[otw["priority"], "cartons"].sum()))])
    q = st.text_input("🔍 Quick Search", placeholder="Search size, color, vendor...",
                      label_visibility="collapsed")
    t1, t2 = st.columns(2)
    manage = t1.toggle("🛠 Receive / Edit Mode", key="manage")
    only_pri = t2.toggle("⭐ Priority Only", value=True, key="only_pri")
    d = otw[otw["priority"]] if only_pri else otw
    cats = CATEGORIES + sorted(set(d["category"]) - set(CATEGORIES))

    if q.strip():
        res = search(d, q)
        if res.empty:
            st.info("No items found.")
        for cat in cats:
            dc = res[res["category"] == cat]
            if dc.empty:
                continue
            st.subheader(cat)
            render_list(dc, manage, f"s{cat}_")
            st.success(f"{cat} Total: {int(dc['cartons'].sum())} cartons")
    else:
        for cat, ctab in zip(cats, st.tabs(cats)):
            with ctab:
                dc = d[d["category"] == cat]
                if dc.empty:
                    st.info("No priority items. Turn off ⭐ filter to view all."
                            if only_pri else "No stock on the way in this category.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                st.success(f"{cat} Total: {int(dc['cartons'].sum())} cartons")

# ---------- NAYA BILL ----------
with tabs[1]:
    ss = st.session_state
    if "draft" not in ss:
        ss["draft"], ss["draft_ok"] = load_draft()
    dr = ss["draft"]
    for k_ in ("vk", "ak", "xk", "bk", "dk"):
        ss.setdefault(k_, 0)
    for list_k in ("del_vendors", "del_sizes", "del_colors", "new_sizes", "new_colors"):
        dr.setdefault(list_k, [])

    st.subheader("Professional Order Entry")
    st.caption("🔒 **Cloud Draft Sync Active:** Data is saved automatically. Safe against app switching.")

    # --- Vendor Selection + Dustbin
    raw_vendors = {v for v in alld["vendor"] if v} | ({dr["vendor"]} if dr["vendor"] else set())
    vend_opts = sorted(raw_vendors - set(dr["del_vendors"]), key=str.lower)
    vidx = vend_opts.index(dr["vendor"]) + 1 if dr["vendor"] in vend_opts else None

    vc1, vc2 = st.columns([6, 1])
    vchoice = vc1.selectbox("Vendor Name", [NEW] + vend_opts, index=vidx,
                            placeholder="Select Vendor", key=f"b_vendor{ss['vk']}")
    vc2.write("")
    vc2.write("")
    if vc2.button("🗑️", key="del_v_btn", disabled=not bool(vchoice and vchoice != NEW), help="Remove Vendor"):
        if vchoice not in dr["del_vendors"]:
            dr["del_vendors"].append(vchoice)
        dr["vendor"] = ""
        save_draft()
        ss["vk"] += 1
        st.rerun()

    if vchoice == NEW:
        vendor = clean_text(st.text_input("Enter new vendor name", key=f"b_vendor_new{ss['vk']}"))
        if vendor in dr["del_vendors"]:
            dr["del_vendors"].remove(vendor)
    else:
        vendor = vchoice or ""
    if vendor != dr["vendor"]:
        dr["vendor"] = vendor
        save_draft()

    # --- Category Radio Tabs
    cat = st.radio("Category", CATEGORIES,
                   index=CATEGORIES.index(dr["category"]) if dr["category"] in CATEGORIES else 0,
                   horizontal=True, key="b_cat")
    if cat != dr["category"]:
        dr["category"] = cat
        save_draft()

    in_cat = alld[alld["category"] == cat]
    pool = in_cat if not in_cat.empty else alld

    raw_sizes = ({x for x in pool["size"] if x} | set(dr["new_sizes"])) - set(dr["del_sizes"])
    raw_colors = ({x for x in pool["color"] if x} | set(dr["new_colors"])) - set(dr["del_colors"])
    size_opts = sorted(raw_sizes, key=size_key)
    color_opts = sorted(raw_colors, key=str.lower)

    # --- Add Line Item Controls
    st.markdown("##### ➕ Add Line Item")
    
    sc1, sc2 = st.columns([6, 1])
    sidx = size_opts.index(dr["size"]) if dr["size"] in size_opts else None
    size = sc1.selectbox("Size", size_opts, index=sidx, placeholder="Select Size", key=f"b_size_{cat}_{ss['ak']}")
    sc2.write("")
    sc2.write("")
    if sc2.button("🗑️", key="del_s_btn", disabled=not bool(size), help="Remove Size"):
        if size in dr["new_sizes"]:
            dr["new_sizes"].remove(size)
        if size not in dr["del_sizes"]:
            dr["del_sizes"].append(size)
        if dr["size"] == size:
            dr["size"] = ""
        save_draft()
        ss["ak"] += 1
        st.rerun()

    cc1, cc2 = st.columns([6, 1])
    color = cc1.selectbox("Color", color_opts, index=None, placeholder="Select Color",
                          key=f"b_color_{ss['ak']}")
    cc2.write("")
    cc2.write("")
    if cc2.button("🗑️", key="del_c_btn", disabled=not bool(color), help="Remove Color"):
        if color in dr["new_colors"]:
            dr["new_colors"].remove(color)
        if color not in dr["del_colors"]:
            dr["del_colors"].append(color)
        save_draft()
        ss["ak"] += 1
        st.rerun()

    n = st.number_input("Cartons Quantity", min_value=1, step=1, value=None,
                        placeholder="Enter cartons", key=f"b_n_{ss['ak']}")
    pri = st.checkbox("⭐ Priority Maal", key=f"b_pri_{ss['ak']}")
    
    if st.button("➕ Add to Bill", type="primary", disabled=not (size and color and n)):
        dr["lines"].append({"category": cat, "size": size, "color": color,
                            "cartons": int(n), "priority": bool(pri)})
        dr["size"] = size
        save_draft()
        ss["ak"] += 1
        st.rerun()

    with st.expander("➕ Add New Size / Color"):
        e1, e2 = st.columns(2)
        ns = clean_size(e1.text_input("New Size", key=f"ns{ss['xk']}"))
        nc = clean_text(e2.text_input("New Color", key=f"nc{ss['xk']}"))
        if st.button("Add Option", key="add_opt", disabled=not (ns or nc)):
            if ns:
                if ns in dr["del_sizes"]: dr["del_sizes"].remove(ns)
                if ns not in dr["new_sizes"]: dr["new_sizes"].append(ns)
            if nc:
                if nc in dr["del_colors"]: dr["del_colors"].remove(nc)
                if nc not in dr["new_colors"]: dr["new_colors"].append(nc)
            save_draft()
            ss["xk"] += 1
            st.rerun()

    with st.expander("⚡ Bulk Quick Entry"):
        st.caption("Format: `size color cartons` (Example: `4 hopo 20`)")
        raw = st.text_area("Bulk text", key=f"bulk{ss['bk']}", height=100,
                           placeholder="4 hopo 20\n6 black 15", label_visibility="collapsed")
        if st.button("Process Bulk Lines ✔", key="bulk_btn", disabled=not raw.strip()):
            added, bad = [], []
            for ln in raw.splitlines():
                t = ln.replace(",", " ").split()
                if not t: continue
                if len(t) >= 3 and t[-1].isdigit() and int(t[-1]) > 0:
                    added.append({"category": cat,
                                  "size": canon(clean_size(t[0]), size_opts),
                                  "color": canon(clean_text(" ".join(t[1:-1])), color_opts),
                                  "cartons": int(t[-1]), "priority": False})
                else:
                    bad.append(ln.strip())
            dr["lines"] += added
            save_draft()
            ss["bk"] += 1
            ss["msg"] = f"{len(added)} lines added successfully ✅"
            st.rerun()

    # --- Live Bill Summary ---
    lines = dr["lines"]
    if lines:
        st.markdown(f"##### 🧾 Active Bill Summary — **{vendor or '⚠️ Vendor Required'}**")
        st.dataframe(pd.DataFrame([{"#": i + 1, "Cat": l["category"], "Size": l["size"],
                                    "Color": l["color"], "Cartons": l["cartons"],
                                    "⭐": "⭐" if l["priority"] else ""}
                                   for i, l in enumerate(lines)]), hide_index=True)
        st.markdown(f"**Total Cartons: {sum(l['cartons'] for l in lines)} • Total Lines: {len(lines)}**")

        r1, r2 = st.columns(2)
        which = r1.selectbox("Select line to remove", list(range(1, len(lines) + 1)), index=None,
                             placeholder="Select line #", key=f"del_{ss['dk']}")
        r2.write("")
        r2.write("")
        if r2.button("🗑 Remove Line", disabled=which is None):
            lines.pop(which - 1)
            save_draft()
            ss["dk"] += 1
            st.rerun()

        if st.button("💾 Finalize & Save Bill", type="primary", disabled=not vendor):
            agg = {}
            for l in lines:
                k = (l["category"], l["size"], l["color"])
                a = agg.get(k, (0, False))
                agg[k] = (a[0] + l["cartons"], a[1] or l["priority"])
            rows = [{"vendor": vendor, "category": k[0], "size": k[1], "color": k[2],
                     "cartons": v[0], "priority": v[1]} for k, v in agg.items()]
            try:
                db().table("orders").insert(rows).execute()
            except Exception as e:
                st.error("Save failed. Draft is secured locally/cloud, try again.")
                st.caption(str(e))
                st.stop()
            
            dr["lines"], dr["vendor"] = [], ""
            save_draft()
            ss["vk"] += 1
            ss["dk"] += 1
            ss["msg"] = f"Bill saved successfully for {vendor}! 🎉"
            st.rerun()
        if not vendor:
            st.caption("⚠️ Please select a Vendor before saving the bill.")

        with st.expander("🧹 Clear Draft Bill"):
            if st.button("Discard all current lines", key="clear_draft"):
                dr["lines"] = []
                save_draft()
                st.rerun()

# ---------- HISTORY ----------
with tabs[2]:
    st.subheader("Received Stock Archive")
    st.session_state.setdefault("hk", 0)
    hk = st.session_state["hk"]
    rec = alld[alld["status"] == "received"]
    f1, f2 = st.columns(2)
    fc = f1.selectbox("Filter Category", ["Sab"] + CATEGORIES, key="h_cat")
    hq = f2.text_input("🔍 Search History", key="h_q")
    if fc != "Sab":
        rec = rec[rec["category"] == fc]
    if hq.strip():
        rec = search(rec, hq)
    rec = sort_df(rec)

    if rec.empty:
        st.info("No received history available.")
    else:
        view = rec[["id", "category", "size", "color", "vendor", "cartons", "received_on"]].copy()
        view.insert(0, "Select", False)
        edited = st.data_editor(
            view, hide_index=True, key=f"hist_{hk}_{fc}_{hq}",
            column_config={"id": None, "Select": st.column_config.CheckboxColumn("✔")},
            disabled=[c for c in view.columns if c != "Select"],
        )
        ids = [int(x) for x in edited.loc[edited["Select"], "id"]]
        st.caption(f"{len(ids)} selected • Total Cartons: {int(rec['cartons'].sum())}")
        if st.button("↩️ Revert to On the Way", disabled=not ids):
            db().table("orders").update({"status": "on_the_way", "received_on": None}) \
                .in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = "Items reverted to On the way ✅"
            st.rerun()
        sure = st.checkbox("Confirm permanent deletion", key=f"h_sure{hk}")
        if st.button("🗑️ Delete Selected History", disabled=not (ids and sure)):
            db().table("orders").delete().in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = "Selected history deleted 🗑️"
            st.rerun()

    st.subheader("Backup Data")
    st.download_button(
        "⬇️ Download CSV Backup",
        alld.drop(columns=["size_num"]).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"stock_backup_{date.today()}.csv",
        mime="text/csv",
    )