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
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="centered")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 0.5rem; padding-bottom: 5rem; max-width: 720px;}

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

button[data-baseweb="tab"] {font-weight: 600; padding: .5rem 0.9rem; font-size: 0.88rem;}

/* Custom Box Style for Filter Tab */
.stock-box {
    border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc;
    padding: 0.8rem 1rem; margin-bottom: 0.6rem; display: flex;
    justify-content: space-between; align-items: center; box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.stock-box .c-name {font-weight: 600; color: #1e293b; font-size: 1.05rem;}
.stock-box .c-qty {font-weight: 700; color: #0f172a; font-size: 1.1rem; background: #e2e8f0; padding: 0.2rem 0.7rem; border-radius: 8px;}
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
def load_draft():
    base = {
        "vendor": "",
        "category": CATEGORIES[0],
        "size": "",
        "color": "",
        "lines": [],
        "del_vendors": [],
        "del_sizes": {},
        "del_colors": {},
    }
    try:
        rows = db().table("drafts").select("*").eq("key", "main").execute().data
        if rows and rows[0].get("data"):
            base.update(rows[0]["data"])
        if not isinstance(base.get("del_sizes"), dict):
            base["del_sizes"] = {}
        if not isinstance(base.get("del_colors"), dict):
            base["del_colors"] = {}
        if not isinstance(base.get("del_vendors"), list):
            base["del_vendors"] = []
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


def smart_selectbox(label, options, value, key):
    opts = list(options)
    if value and value not in opts:
        opts = [value] + opts
    idx = opts.index(value) if value in opts else None
    kwargs = {"index": idx, "placeholder": f"{label} chunein ya naya likhein", "key": key}
    if "accept_new_options" in inspect.signature(st.selectbox).parameters:
        kwargs["accept_new_options"] = True
    return st.selectbox(label, opts, **kwargs)


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
                    st.write(f"{r['vendor'] or NO_VENDOR}: {r['cartons']} • Ordered: {r['ordered_on']}")
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
                        nsz = st.text_input("Size", value=r["size"], key=f"{kp}sz{r['id']}")
                        ncol = st.text_input("Color", value=r["color"], key=f"{kp}cl{r['id']}")
                        nc = st.number_input("Cartons", min_value=1, step=1,
                                             value=max(int(r["cartons"]), 1), key=f"{kp}c{r['id']}")
                        npri = st.checkbox("⭐ Priority", value=bool(r["priority"]),
                                           key=f"{kp}s{r['id']}")
                        if st.button("Save", key=f"{kp}sv{r['id']}"):
                            update_rows([r["id"]], {
                                "vendor": clean_text(nv),
                                "size": clean_size(nsz),
                                "color": clean_text(ncol),
                                "cartons": int(nc),
                                "priority": bool(npri)
                            })
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
        st.session_state["msg"] = "Wapas On the way kar diya ✅"
        st.rerun()
    if u2.button("✖ Theek hai", key="undo_x"):
        del st.session_state["last_rcv"]
        st.rerun()

# --- TABS: Added Stock Search & Vendor Bill as separate tabs ---
tabs = st.tabs(["🔍 Stock Search", "🏠 Home", "🧾 Vendor Bill", "➕ Naya Bill", "📜 History"])

# ---------- TAB 1: STOCK SEARCH (Filter by Category & Size) ----------
with tabs[0]:
    st.subheader("Category & Size Filter")
    
    # 1. Select Category
    s_cat = st.radio("Category Chunein", CATEGORIES, horizontal=True, key="search_cat")
    cat_otw = otw[otw["category"] == s_cat]
    
    if cat_otw.empty:
        st.info(f"'{s_cat}' category mein koi on-the-way stock nahi hai.")
    else:
        # 2. Select Size from available sizes
        available_sizes = sorted(cat_otw["size"].unique(), key=size_key)
        s_size = st.selectbox("Size Chunein", available_sizes, placeholder="Size select karein...", key="search_size")
        
        if s_size:
            size_data = cat_otw[cat_otw["size"] == s_size].copy()
            # Group by color and sum cartons, then sort descending by cartons quantity
            color_summary = size_data.groupby("color")["cartons"].sum().reset_index()
            color_summary = color_summary.sort_values(by="cartons", ascending=False)
            
            st.markdown(f"### 📊 Size: **{s_size}** ({s_cat})")
            
            if color_summary.empty:
                st.info("Is size mein koi color nahi mila.")
            else:
                for _, row in color_summary.iterrows():
                    c_col = row["color"]
                    c_qty = int(row["cartons"])
                    st.markdown(
                        f'<div class="stock-box"><span class="c-name">{c_col}</span><span class="c-qty">{c_qty} cartons</span></div>',
                        unsafe_allow_html=True
                    )

# ---------- TAB 2: HOME ----------
with tabs[1]:
    # Top corner toggles for clean look
    tc1, tc2 = st.columns(2)
    manage = tc1.toggle("🛠 Receive / Edit", key="manage")
    only_pri = tc2.toggle("⭐ Sirf Priority", value=True, key="only_pri")
    
    q = st.text_input("🔍 Search", placeholder="Size, color ya vendor search karein...",
                      label_visibility="collapsed")
    
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

# ---------- TAB 3: VENDOR BILL VIEWER ----------
with tabs[2]:
    st.subheader("Vendor-Wise Pora Bill")
    all_vendors = sorted([v for v in otw["vendor"].unique() if v])
    selected_v = st.selectbox("Vendor Chunein", all_vendors, placeholder="Vendor select karein", key="v_bill_sel")
    if selected_v:
        v_data = otw[otw["vendor"] == selected_v].copy()
        v_data = sort_df(v_data)
        st.markdown(f"### 📋 Bill Summary: **{selected_v}**")
        
        display_rows = []
        for _, row in v_data.iterrows():
            display_rows.append({
                "Category": row["category"],
                "Size": row["size"],
                "Color": row["color"],
                "Cartons": row["cartons"],
                "Priority": "⭐" if row["priority"] else "",
                "Ordered On": row["ordered_on"]
            })
        st.dataframe(pd.DataFrame(display_rows), hide_index=True)
        st.info(f"**Total Cartons for {selected_v}: {int(v_data['cartons'].sum())}**")

# ---------- TAB 4: NAYA BILL ----------
with tabs[3]:
    ss = st.session_state
    if "draft" not in ss:
        ss["draft"], ss["draft_ok"] = load_draft()
    dr = ss["draft"]
    ss.setdefault("ak", 0)
    
    if not isinstance(dr.get("del_sizes"), dict):
        dr["del_sizes"] = {}
    if not isinstance(dr.get("del_colors"), dict):
        dr["del_colors"] = {}
    if not isinstance(dr.get("del_vendors"), list):
        dr["del_vendors"] = []
    dr.setdefault("lines", [])

    st.caption("🔒 Auto-save on hai — dropdown mein hi seedha naya size ya color type kar sakte hain.")

    raw_vendors = {v for v in alld["vendor"] if v} - set(dr["del_vendors"])
    vend_opts = sorted(raw_vendors, key=str.lower)
    picked_v = smart_selectbox("Vendor Name", vend_opts, dr.get("vendor", ""), key=f"v_sel_{ss['ak']}")
    vendor = clean_text(picked_v) if picked_v else ""
    if vendor != dr.get("vendor", ""):
        dr["vendor"] = vendor
        if vendor in dr["del_vendors"]:
            dr["del_vendors"].remove(vendor)
        save_draft()

    cat = st.radio(
        "Category", CATEGORIES,
        index=CATEGORIES.index(dr["category"]) if dr.get("category") in CATEGORIES else 0,
        horizontal=True, key="cart_cat"
    )
    if cat != dr.get("category"):
        dr["category"] = cat
        save_draft()

    cat_pool = alld[alld["category"] == cat]
    cat_del_sizes = dr["del_sizes"].get(cat, [])
    cat_del_colors = dr["del_colors"].get(cat, [])

    sheet_sizes = {clean_size(l["size"]) for l in dr["lines"] if l.get("category") == cat}
    sheet_colors = {clean_text(l["color"]) for l in dr["lines"] if l.get("category") == cat}

    size_opts = sorted(
        ({x for x in cat_pool["size"] if x} | sheet_sizes) - set(cat_del_sizes),
        key=size_key
    )
    color_opts = sorted(
        ({x for x in cat_pool["color"] if x} | sheet_colors) - set(cat_del_colors),
        key=str.lower
    )

    st.markdown("##### ➕ Item Add Karein")
    
    sz_raw = smart_selectbox("Size", size_opts, "", key=f"c_sz_{ss['ak']}")
    sz_val = clean_size(sz_raw) if sz_raw else ""

    cl_raw = smart_selectbox("Color", color_opts, "", key=f"c_cl_{ss['ak']}")
    cl_val = clean_text(cl_raw) if cl_raw else ""

    cartons_val = st.number_input("Cartons Quantity", min_value=1, step=1, value=None, placeholder="Carton count", key=f"c_qty_{ss['ak']}")
    pri_val = st.checkbox("⭐ Priority Maal", key=f"c_pri_{ss['ak']}")

    if st.button("➕ Bill mein jorein", type="primary", disabled=not (sz_val and cl_val and cartons_val)):
        dr["lines"].append({
            "category": cat,
            "size": sz_val,
            "color": cl_val,
            "cartons": int(cartons_val),
            "priority": bool(pri_val)
        })
        save_draft()
        ss["ak"] += 1
        st.rerun()

    lines = dr.get("lines", [])
    if lines:
        st.markdown(f"##### 🧾 Current Bill — **{vendor or '⚠️ Vendor select nahi kiya'}**")
        table_data = []
        for i, l in enumerate(lines):
            table_data.append({
                "#": i + 1,
                "Cat": l["category"],
                "Size": l["size"],
                "Color": l["color"],
                "Cartons": l["cartons"],
                "⭐": "⭐" if l["priority"] else ""
            })
        st.dataframe(pd.DataFrame(table_data), hide_index=True)
        
        total_cartons = sum(l["cartons"] for l in lines)
        st.markdown(f"**Total Cartons: {total_cartons} • Total Items: {len(lines)}**")

        del_col1, del_col2 = st.columns(2)
        rem_idx = del_col1.selectbox("Line # hatane ke liye", list(range(1, len(lines) + 1)), index=None, placeholder="Line select karein", key=f"rem_line_{ss['ak']}")
        del_col2.write("")
        del_col2.write("")
        if del_col2.button("🗑️ Selected Line Hatayen", disabled=rem_idx is None):
            lines.pop(rem_idx - 1)
            save_draft()
            ss["ak"] += 1
            st.rerun()

        if st.button("💾 Poora Bill Save Karein", type="primary", disabled=not vendor):
            agg = {}
            for l in lines:
                k = (l["category"], l["size"], l["color"])
                prev = agg.get(k, (0, False))
                agg[k] = (prev[0] + l["cartons"], prev[1] or l["priority"])
            
            today_str = str(date.today())
            rows_to_insert = [
                {
                    "vendor": vendor,
                    "category": k[0],
                    "size": k[1],
                    "color": k[2],
                    "cartons": v[0],
                    "priority": v[1],
                    "ordered_on": today_str
                }
                for k, v in agg.items()
            ]
            try:
                db().table("orders").insert(rows_to_insert).execute()
            except Exception as e:
                st.error("Save nahi ho saka. Draft mein mehfooz hai.")
                st.caption(str(e))
                st.stop()

            dr["lines"] = []
            dr["vendor"] = ""
            save_draft()
            ss["ak"] += 1
            st.cache_resource.clear()
            st.session_state["msg"] = f"{vendor} ka bill save ho gaya! 🎉"
            st.rerun()
        
        if not vendor:
            st.caption("⚠️ Save karne se pehle upar Vendor select karna lazmi hai.")

        if st.button("🧹 Bill Clear Karein"):
            dr["lines"] = []
            save_draft()
            ss["ak"] += 1
            st.rerun()

# ---------- TAB 5: HISTORY ----------
with tabs[4]:
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