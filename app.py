import hashlib
import inspect
import re
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

# ======================= SETTINGS =======================
CATEGORIES = ["Crystal", "Pod", "Shelper"]   # nayi category yahan add karein
COLS = ["id", "category", "vendor", "size", "color", "cartons",
        "priority", "status", "ordered_on", "received_on"]
NO_VENDOR = "(vendor nahi likha)"
CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}
DEFAULT_ROWS = 5
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="centered")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 0.8rem; padding-bottom: 5rem; max-width: 720px;}

h1 {font-size: 1.3rem !important; font-weight: 700; color: #0f172a; margin-bottom: 0.3rem;}
h3 {font-size: 1.1rem !important; font-weight: 600; color: #1e293b;}
h5 {font-size: 0.9rem !important; font-weight: 600; color: #334155; margin-top: .5rem;}

.stButton > button, .stDownloadButton > button {
    min-height: 2.9rem; border-radius: 10px; font-weight: 600; width: 100%;
    border: 1px solid #cbd5e1; background-color: #ffffff; color: #1e293b;
}
.stPrimaryButton > button {
    background-color: #0f172a !important; color: #ffffff !important; border: none !important;
}

[data-baseweb="select"] > div, div[data-baseweb="input"] input {
    border-radius: 10px !important; min-height: 2.8rem !important;
}

[data-testid="stExpander"] details {
    border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;
    margin-bottom: 0.4rem;
}
[data-testid="stExpander"] summary {padding: .7rem .9rem; font-weight: 600; color: #1e293b;}

button[data-baseweb="tab"] {font-weight: 600; padding: .5rem 1rem; font-size: 0.9rem;}

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


# ---------- Cloud Draft (Auto-Save) ----------
def empty_sheet(n=DEFAULT_ROWS):
    return [{"Size": "", "Color": "", "Cartons": None, "⭐": False} for _ in range(n)]


def load_draft():
    base = {
        "vendor": "",
        "category": CATEGORIES[0],
        "sheet": empty_sheet(),
        "del_vendors": [],
        "del_sizes": {},   # Category-wise deleted sizes
        "del_colors": {},  # Category-wise deleted colors
    }
    try:
        rows = db().table("drafts").select("*").eq("key", "main").execute().data
        if rows and rows[0].get("data"):
            base.update(rows[0]["data"])
        if not base.get("sheet"):
            base["sheet"] = empty_sheet()
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
    st.error("Database connection error. Check Supabase project.")
    st.caption(str(e))
    st.stop()

otw = alld[alld["status"] == "on_the_way"]


# ---------- Helpers ----------
def size_key(s):
    m = re.search(r"\d+\.?\d*", str(s))
    return (float(m.group()) if m else 9999.0, str(s))


def clean_text(s):
    return " ".join(str(s).strip().split()).title()


def clean_size(s):
    s = str(s).strip().lower().replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        s += "mm"
    return s


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


def smart_selectbox(label, options, value, key):
    opts = list(options)
    if value and value not in opts:
        opts = [value] + opts
    idx = opts.index(value) if value in opts else None
    kwargs = {"index": idx, "placeholder": f"{label} chunein ya likhein", "key": key}
    if "accept_new_options" in inspect.signature(st.selectbox).parameters:
        kwargs["accept_new_options"] = True
    return st.selectbox(label, opts, **kwargs)


def smart_col(label, options):
    sig = inspect.signature(st.column_config.SelectboxColumn).parameters
    if "accept_new_options" in sig:
        return st.column_config.SelectboxColumn(
            label, options=list(options), accept_new_options=True, width="medium"
        )
    return st.column_config.SelectboxColumn(
        label, options=list(options), width="medium"
    )


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
                            st.session_state["msg"] = "Updated ✅"
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
        st.session_state["msg"] = "Wapas On the way kar diya ✅"
        st.rerun()
    if u2.button("✖ Theek hai", key="undo_x"):
        del st.session_state["last_rcv"]
        st.rerun()

tabs = st.tabs(["🏠 Home", "➕ Naya Bill", "📜 History"])

# ---------- HOME ----------
with tabs[0]:
    stat_cards([("Total cartons", int(otw["cartons"].sum())),
                ("Items", otw.groupby(["category", "size", "color"]).ngroups),
                ("⭐ Priority", int(otw.loc[otw["priority"], "cartons"].sum()))])
    q = st.text_input("🔍 Search", placeholder="Size, color ya vendor search karein...",
                      label_visibility="collapsed")
    t1, t2 = st.columns(2)
    manage = t1.toggle("🛠 Receive / Edit", key="manage")
    only_pri = t2.toggle("⭐ Sirf Priority", value=True, key="only_pri")
    d = otw[otw["priority"]] if only_pri else otw
    cats = CATEGORIES + sorted(set(d["category"]) - set(CATEGORIES))

    if q.strip():
        res = search(d, q)
        if res.empty:
            st.info("Koi maal nahi mila.")
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
                    st.info("Priority wala koi maal nahi. Sab dekhne ke liye ⭐ switch band karein."
                            if only_pri else "Is category mein koi maal on the way nahi.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                st.success(f"{cat} Total: {int(dc['cartons'].sum())} cartons")

# ---------- NAYA BILL (CATEGORY-WISE FILTERED) ----------
with tabs[1]:
    ss = st.session_state
    if "draft" not in ss:
        ss["draft"], ss["draft_ok"] = load_draft()
    dr = ss["draft"]
    ss.setdefault("sk", 0)
    dr.setdefault("del_vendors", [])
    dr.setdefault("del_sizes", {})
    dr.setdefault("del_colors", {})
    dr.setdefault("sheet", empty_sheet())

    st.caption("🔒 Auto-save on hai — har category ke apne size aur colors alag dropdown mein show honge.")

    # 1. Vendor Selection
    raw_vendors = {v for v in alld["vendor"] if v} - set(dr["del_vendors"])
    vend_opts = sorted(raw_vendors, key=str.lower)
    picked_v = smart_selectbox("Vendor", vend_opts, dr.get("vendor", ""), key=f"v_sel_{ss['sk']}")
    vendor = clean_text(picked_v) if picked_v else ""
    if vendor != dr.get("vendor", ""):
        dr["vendor"] = vendor
        if vendor in dr["del_vendors"]:
            dr["del_vendors"].remove(vendor)
        save_draft()

    # 2. Category Selection (Radio)
    cat = st.radio(
        "Category", CATEGORIES,
        index=CATEGORIES.index(dr["category"]) if dr.get("category") in CATEGORIES else 0,
        horizontal=True, key="b_cat"
    )
    if cat != dr.get("category"):
        dr["category"] = cat
        save_draft()

    # --- STRICT CATEGORY FILTERING ---
    # Sirf usi category ka data uthayega jo select hui hai
    cat_pool = alld[alld["category"] == cat]
    
    cat_del_sizes = dr["del_sizes"].get(cat, [])
    cat_del_colors = dr["del_colors"].get(cat, [])

    sheet_sizes = {clean_size(r["Size"]) for r in dr["sheet"] if str(r.get("Size", "")).strip()}
    sheet_colors = {clean_text(r["Color"]) for r in dr["sheet"] if str(r.get("Color", "")).strip()}

    size_opts = sorted(
        ({x for x in cat_pool["size"] if x} | sheet_sizes) - set(cat_del_sizes),
        key=size_key
    )
    color_opts = sorted(
        ({x for x in cat_pool["color"] if x} | sheet_colors) - set(cat_del_colors),
        key=str.lower
    )

    # 3. Excel-Style Sheet
    df_init = pd.DataFrame(dr["sheet"])
    for col, default in [("Size", ""), ("Color", ""), ("Cartons", None), ("⭐", False)]:
        if col not in df_init.columns:
            df_init[col] = default
    df_init = df_init[["Size", "Color", "Cartons", "⭐"]]
    df_init["Size"] = df_init["Size"].fillna("").astype(str)
    df_init["Color"] = df_init["Color"].fillna("").astype(str)
    df_init["Cartons"] = pd.to_numeric(df_init["Cartons"], errors="coerce")
    df_init["⭐"] = df_init["⭐"].fillna(False).astype(bool)

    edited_df = st.data_editor(
        df_init,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"excel_grid_{cat}_{ss['sk']}",
        column_config={
            "Size": smart_col("Size", size_opts),
            "Color": smart_col("Color", color_opts),
            "Cartons": st.column_config.NumberColumn("Cartons", min_value=1, step=1, format="%d"),
            "⭐": st.column_config.CheckboxColumn("⭐", default=False, width="small"),
        },
    )

    new_sheet = []
    valid_rows = []
    for _, row in edited_df.iterrows():
        s_raw = "" if pd.isna(row["Size"]) else str(row["Size"]).strip()
        c_raw = "" if pd.isna(row["Color"]) else str(row["Color"]).strip()
        qty_val = None if pd.isna(row["Cartons"]) else int(row["Cartons"])
        pri_val = bool(row["⭐"]) if not pd.isna(row["⭐"]) else False
        new_sheet.append({"Size": s_raw, "Color": c_raw, "Cartons": qty_val, "⭐": pri_val})
        if s_raw and c_raw and qty_val and qty_val > 0:
            valid_rows.append({
                "category": cat,
                "size": clean_size(s_raw),
                "color": clean_text(c_raw),
                "cartons": qty_val,
                "priority": pri_val,
            })

    if new_sheet != dr["sheet"]:
        dr["sheet"] = new_sheet
        save_draft()

    total_cartons = sum(r["cartons"] for r in valid_rows)
    st.markdown(f"**Total: {total_cartons} cartons • {len(valid_rows)} items**")

    c_save, c_clear = st.columns([3, 1])
    if c_save.button("💾 Bill Save Karein", type="primary", disabled=not (vendor and valid_rows)):
        agg = {}
        for r in valid_rows:
            k = (r["category"], r["size"], r["color"])
            prev = agg.get(k, (0, False))
            agg[k] = (prev[0] + r["cartons"], prev[1] or r["priority"])
        rows_to_insert = [
            {"vendor": vendor, "category": k[0], "size": k[1], "color": k[2],
             "cartons": v[0], "priority": v[1]}
            for k, v in agg.items()
        ]
        try:
            db().table("orders").insert(rows_to_insert).execute()
        except Exception as e:
            st.error("Save nahi ho saka. Bill draft mein mehfooz hai.")
            st.caption(str(e))
            st.stop()

        # Restore cleaned items if re-added
        for r in valid_rows:
            if r["size"] in dr["del_sizes"].get(cat, []):
                dr["del_sizes"][cat].remove(r["size"])
            if r["color"] in dr["del_colors"].get(cat, []):
                dr["del_colors"][cat].remove(r["color"])

        dr["sheet"] = empty_sheet()
        dr["vendor"] = ""
        save_draft()
        ss["sk"] += 1
        st.cache_resource.clear()
        ss["msg"] = f"{vendor} ka bill save ho gaya ({total_cartons} cartons) ✅"
        st.rerun()

    if c_clear.button("🧹 Clear", disabled=not valid_rows):
        dr["sheet"] = empty_sheet()
        save_draft()
        ss["sk"] += 1
        st.rerun()

    if not vendor and valid_rows:
        st.caption("⚠️ Save karne ke liye upar Vendor chunein ya likhein.")

    # --- Remove Unwanted Size / Color / Vendor Option ---
    with st.expander("🗑️ Saved Vendor / Size / Color list se hatayen"):
        d1, d2, d3 = st.columns(3)
        dv = d1.selectbox("Vendor", vend_opts, index=None, placeholder="Chunein", key=f"dv_{ss['sk']}")
        if d1.button("Vendor Hatayen", disabled=not dv, key="btn_dv"):
            dr["del_vendors"].append(dv)
            if dr.get("vendor") == dv:
                dr["vendor"] = ""
            save_draft()
            ss["sk"] += 1
            st.rerun()

        ds = d2.selectbox(f"Size ({cat})", size_opts, index=None, placeholder="Chunein", key=f"ds_{ss['sk']}")
        if d2.button("Size Hatayen", disabled=not ds, key="btn_ds"):
            dr["del_sizes"].setdefault(cat, []).append(ds)
            save_draft()
            ss["sk"] += 1
            st.rerun()

        dc_item = d3.selectbox(f"Color ({cat})", color_opts, index=None, placeholder="Chunein", key=f"dc_{ss['sk']}")
        if d3.button("Color Hatayen", disabled=not dc_item, key="btn_dc"):
            dr["del_colors"].setdefault(cat, []).append(dc_item)
            save_draft()
            ss["sk"] += 1
            st.rerun()

# ---------- HISTORY ----------
with tabs[2]:
    st.subheader("Receive ho chuka maal")
    st.session_state.setdefault("hk", 0)
    hk = st.session_state["hk"]
    rec = alld[alld["status"] == "received"]
    f1, f2 = st.columns(2)
    fc = f1.selectbox("Category", ["Sab"] + CATEGORIES, key="h_cat")
    hq = f2.text_input("🔍 Search History", key="h_q")
    if fc != "Sab":
        rec = rec[rec["category"] == fc]
    if hq.strip():
        rec = search(rec, hq)
    rec = sort_df(rec)

    if rec.empty:
        st.info("Koi received maal nahi.")
    else:
        view = rec[["id", "category", "size", "color", "vendor", "cartons", "received_on"]].copy()
        view.insert(0, "Select", False)
        edited = st.data_editor(
            view, hide_index=True, key=f"hist_{hk}_{fc}_{hq}",
            column_config={"id": None, "Select": st.column_config.CheckboxColumn("✔")},
            disabled=[c for c in view.columns if c != "Select"],
        )
        ids = [int(x) for x in edited.loc[edited["Select"], "id"]]
        st.caption(f"{len(ids)} selected • Total cartons: {int(rec['cartons'].sum())}")
        if st.button("↩️ Wapas On the Way karein", disabled=not ids):
            db().table("orders").update({"status": "on_the_way", "received_on": None}) \
                .in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = "Wapas On the way kar diya ✅"
            st.rerun()
        sure = st.checkbox("Haan, permanent delete karna hai", key=f"h_sure{hk}")
        if st.button("🗑️ Delete Karein", disabled=not (ids and sure)):
            db().table("orders").delete().in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = "Delete ho gaya 🗑️"
            st.rerun()

    st.subheader("Backup")
    st.download_button(
        "⬇️ Download CSV Backup",
        alld.drop(columns=["size_num"]).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"stock_backup_{date.today()}.csv",
        mime="text/csv",
    )