import hashlib
import inspect
import re
import time
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

# ======================= SETTINGS =======================
CATEGORIES = ["Crystal", "Pod", "Shelper", "Qancha", "Marble", "Sitara", "Article", "Bicon", "Pearl"]
COLS = ["id", "bill_id", "category", "vendor", "size", "color", "cartons",
        "priority", "status", "ordered_on", "received_on"]
GODOWN_COLS = ["id", "category", "size", "color", "cartons"]
NO_VENDOR = "(vendor nahi likha)"
CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="wide")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {
    padding-top: 0.5rem;
    padding-bottom: 5rem;
    max-width: 820px;
    margin: auto;
}

h1 {font-size: 1.3rem !important; font-weight: 700; color: #0f172a; margin-bottom: 0.3rem;}
h3 {font-size: 1.05rem !important; font-weight: 600; color: #1e293b;}
h5 {font-size: 0.9rem !important; font-weight: 600; color: #334155; margin-top: .4rem;}

.stButton > button, .stDownloadButton > button {
    min-height: 2.5rem;
    border-radius: 8px;
    font-weight: 600;
    width: 100%;
    border: 1px solid #cbd5e1;
    background-color: #ffffff;
    color: #1e293b;
    padding: 0.25rem 0.5rem;
    transition: all 0.1s ease;
}
.stButton > button:hover {
    border-color: #94a3b8;
    background-color: #f8fafc;
}
.stPrimaryButton > button {
    background-color: #0f172a !important;
    color: #ffffff !important;
    border: none !important;
}

[data-baseweb="select"] > div, div[data-baseweb="input"] input {
    border-radius: 8px !important;
    min-height: 2.5rem !important;
}

[data-testid="stExpander"] details {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background: #ffffff;
    margin-bottom: 0.35rem;
}
[data-testid="stExpander"] summary {
    padding: .6rem .8rem;
    font-weight: 600;
    color: #0f172a;
}

button[data-baseweb="tab"] {
    font-weight: 600;
    padding: .4rem 0.6rem;
    font-size: 0.85rem;
}

.stock-box {
    border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc;
    padding: 0.6rem 0.9rem; margin-bottom: 0.4rem; display: flex;
    justify-content: space-between; align-items: center; font-size: 0.92rem;
}
.stock-box .c-name {font-weight: 600; color: #1e293b;}
.stock-box .c-qty {font-weight: 600; color: #0f172a; background: #e2e8f0; padding: 0.15rem 0.6rem; border-radius: 6px; font-size: 0.85rem;}

.cart-row {
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    border-radius: 8px;
    padding: 0.45rem 0.7rem;
    margin-bottom: 0.3rem;
    font-size: 0.9rem;
    color: #0f172a;
}
.home-line {
    padding: 0.3rem 0;
    font-size: 0.9rem;
    color: #1e293b;
}

@media (max-width: 640px) {
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.3rem !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        min-width: 0 !important;
    }
}
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


# ---------- Database (Fast Caching) ----------
@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


@st.cache_data(ttl=5)
def load_all():
    rows, start = [], 0
    while True:
        res = db().table("orders").select("*").order("id").range(start, start + 999).execute()
        chunk = res.data
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000

    for r in rows:
        if "bill_id" not in r or not r["bill_id"]:
            r["bill_id"] = f"bill_{r['id']}"

    df = pd.DataFrame(rows)
    for col in COLS:
        if col not in df.columns:
            df[col] = None

    df = df[COLS]
    df["cartons"] = pd.to_numeric(df["cartons"]).fillna(0.0)
    df["priority"] = df["priority"].fillna(False).astype(bool)
    for c in ["bill_id", "category", "vendor", "size", "color", "status", "ordered_on", "received_on"]:
        df[c] = df[c].fillna("").astype(str)

    df["size_num"] = pd.to_numeric(
        df["size"].str.extract(r"(\d+\.?\d*)", expand=False), errors="coerce"
    ).fillna(9999)
    return df


@st.cache_data(ttl=5)
def load_godown():
    rows, start = [], 0
    while True:
        try:
            res = db().table("godown_stock").select("*").order("id").range(start, start + 999).execute()
            chunk = res.data
            rows += chunk
            if len(chunk) < 1000:
                break
            start += 1000
        except Exception:
            break
    
    df = pd.DataFrame(rows)
    for col in GODOWN_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[GODOWN_COLS]
    df["cartons"] = pd.to_numeric(df["cartons"]).fillna(0.0)
    for c in ["category", "size", "color"]:
        df[c] = df[c].fillna("").astype(str)
    df["size_num"] = pd.to_numeric(
        df["size"].str.extract(r"(\d+\.?\d*)", expand=False), errors="coerce"
    ).fillna(9999)
    return df


def clear_cache():
    load_all.clear()
    load_godown.clear()


def update_rows(ids, fields):
    db().table("orders").update(fields).in_("id", [int(i) for i in ids]).execute()
    clear_cache()


def delete_row(row_id):
    db().table("orders").delete().eq("id", int(row_id)).execute()
    clear_cache()


# ---------- Cloud Draft (Auto-Save) ----------
def load_draft():
    base = {
        "vendor": "",
        "category": CATEGORIES[0],
        "order_date": str(date.today()),
        "lines": [],
        "del_vendors": [],
        "del_sizes": {},
        "del_colors": {},
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
        pass


try:
    alld = load_all()
    godown_df = load_godown()
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
    kwargs = {"index": idx, "placeholder": f"{label} chunein ya likhein", "key": key}
    if "accept_new_options" in inspect.signature(st.selectbox).parameters:
        kwargs["accept_new_options"] = True
    return st.selectbox(label, opts, **kwargs)


# ---------- Home List ----------
def render_list(d, manage, kp):
    if d.empty:
        st.info("Koi maal nahi mila.")
        return
    d = sort_df(d)
    for (size, color), g in d.groupby(["size", "color"], sort=False):
        star = " ⭐" if g["priority"].any() else ""
        tot_ctn = g['cartons'].sum()
        tot_ctn_str = f"{int(tot_ctn)}" if tot_ctn.is_integer() else f"{tot_ctn}"
        with st.expander(f"{size} {color}{star} — {tot_ctn_str} carton"):
            if manage:
                has_pri = bool(g["priority"].any())
                if st.button("⭐ Priority hatayen" if has_pri else "⭐ Priority lagayen",
                             key=f"{kp}pg{size}_{color}"):
                    update_rows(g["id"].tolist(), {"priority": not has_pri})
                    st.rerun()
                st.divider()

            for _, r in g.iterrows():
                v_name = r["vendor"] or NO_VENDOR
                c_qty = r["cartons"]
                c_qty_str = f"{int(c_qty)}" if c_qty.is_integer() else f"{c_qty}"
                c_col = r["color"]
                ord_date = r["ordered_on"]

                c_info, c_rcv, c_ed, c_del = st.columns([5.2, 1.3, 1.3, 1.1])
                c_info.markdown(
                    f'<div class="home-line">• <b>{v_name}</b> | {c_col} | <b>{c_qty_str} ctn</b> | 📅 {ord_date}</div>',
                    unsafe_allow_html=True
                )

                if c_rcv.button("✅", help="Received mark karein", key=f"{kp}rcv{r['id']}"):
                    update_rows([r["id"]], {"status": "received", "received_on": str(date.today())})
                    st.session_state["last_rcv"] = {
                        "ids": [int(r["id"])],
                        "label": f"{size} {color} ({v_name}: {c_qty_str} carton)"
                    }
                    st.rerun()

                with c_ed.popover("✏️"):
                    nv = st.text_input("Vendor", value=r["vendor"], key=f"{kp}v{r['id']}")
                    nsz = st.text_input("Size", value=r["size"], key=f"{kp}sz{r['id']}")
                    ncol = st.text_input("Color", value=r["color"], key=f"{kp}cl{r['id']}")
                    nc = st.number_input("Cartons", min_value=0.5, step=0.5,
                                         value=float(c_qty), key=f"{kp}c{r['id']}")
                    npri = st.checkbox("⭐ Priority", value=bool(r["priority"]),
                                       key=f"{kp}s{r['id']}")
                    if st.button("Save", key=f"{kp}sv{r['id']}"):
                        update_rows([r["id"]], {
                            "vendor": clean_text(nv),
                            "size": clean_size(nsz),
                            "color": clean_text(ncol),
                            "cartons": float(nc),
                            "priority": bool(npri)
                        })
                        st.session_state["msg"] = "Updated ✅"
                        st.rerun()

                if c_del.button("🗑️", help="Permanent Delete", key=f"{kp}del{r['id']}"):
                    delete_row(r["id"])
                    st.session_state["msg"] = f"{v_name} ({size} {c_col}) delete ho gaya 🗑️"
                    st.rerun()


# ======================= SIDEBAR =======================
with st.sidebar:
    st.markdown("### ⚙️ Master Data & Export")
    unrec_df = otw.sort_values(by=["size_num", "size"])[["ordered_on", "size", "color", "cartons", "category"]].copy()
    unrec_df.columns = ["Date", "Size", "Color", "Carton Quantity", "Category"]
    csv_data = unrec_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Download Unreceived CSV",
        csv_data,
        file_name=f"unreceived_stock_{date.today()}.csv",
        mime="text/csv",
    )


# ======================= HEADER & MENU =======================
head_c1, head_c2 = st.columns([5, 1])
head_c1.title("📦 Stock On The Way")

with head_c2.popover("⚙️ Menu"):
    st.markdown("### Quick Options")
    if st.button("📥 Download Unreceived CSV"):
        st.download_button(
            "Click to Save CSV",
            csv_data,
            file_name=f"unreceived_stock_{date.today()}.csv",
            mime="text/csv"
        )

if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))

if "last_rcv" in st.session_state:
    lr = st.session_state["last_rcv"]
    st.info(f"✅ Received: {lr['label']}")
    u1, u2 = st.columns(2)
    if u1.button("↩️ Undo", key="undo"):
        db().table("orders").update({"status": "on_the_way", "received_on": None}) \
            .in_("id", lr["ids"]).eq("status", "received").execute()
        clear_cache()
        del st.session_state["last_rcv"]
        st.session_state["msg"] = "Wapas On the way kar diya ✅"
        st.rerun()
    if u2.button("✖ Theek hai", key="undo_x"):
        del st.session_state["last_rcv"]
        st.rerun()

TAB_LIST = ["🔍 Stock Search", "🏢 Godown Stock", "🏠 Home", "🧾 Vendor Bill", "➕ Naya Bill", "📜 History"]
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = TAB_LIST[0]

selected_tab = st.radio("Navigation", TAB_LIST, index=TAB_LIST.index(st.session_state["active_tab"]), horizontal=True, label_visibility="collapsed")
st.session_state["active_tab"] = selected_tab
st.markdown("---")

# ---------- TAB 1: STOCK SEARCH (Godown -> On The Way -> Total Breakdown) ----------
if selected_tab == "🔍 Stock Search":
    st.subheader("Stock Search (Godown & On The Way)")
    s_cat = st.radio("Category Chunein", CATEGORIES, horizontal=True, key="search_cat")
    
    cat_otw = otw[otw["category"] == s_cat]
    cat_godown = godown_df[godown_df["category"] == s_cat]

    all_cat_sizes = sorted(list(set(cat_otw["size"].unique()) | set(cat_godown["size"].unique())), key=size_key)

    if not all_cat_sizes:
        st.info(f"'{s_cat}' category mein koi stock mojood nahi hai.")
    else:
        s_size = st.selectbox("Size Chunein", all_cat_sizes, placeholder="Size select karein...", key="search_size")

        if s_size:
            sz_otw = cat_otw[cat_otw["size"] == s_size]
            sz_gdn = cat_godown[cat_godown["size"] == s_size]

            gdn_summary = sz_gdn.groupby("color")["cartons"].sum().to_dict()
            otw_summary = sz_otw.groupby("color")["cartons"].sum().to_dict()

            all_colors = sorted(list(set(gdn_summary.keys()) | set(otw_summary.keys())), key=str.lower)

            st.markdown(f"### 📊 Size: **{s_size}** ({s_cat})")
            if not all_colors:
                st.info("Is size mein koi color nahi mila.")
            else:
                for col in all_colors:
                    g_ctn = gdn_summary.get(col, 0.0)
                    o_ctn = otw_summary.get(col, 0.0)
                    tot_ctn = g_ctn + o_ctn
                    
                    g_str = f"{int(g_ctn)}" if g_ctn.is_integer() else f"{g_ctn}"
                    o_str = f"{int(o_ctn)}" if o_ctn.is_integer() else f"{o_ctn}"
                    tot_str = f"{int(tot_ctn)}" if tot_ctn.is_integer() else f"{tot_ctn}"
                    
                    st.markdown(
                        f'<div class="stock-box"><span class="c-name">{col}</span>'
                        f'<span class="c-qty">🏢 {g_str} | 🚢 {o_str} | Tot: <b>{tot_str} ctn</b></span></div>',
                        unsafe_allow_html=True
                    )

# ---------- TAB 2: GODOWN STOCK (With View/Edit Modes & Add Button) ----------
elif selected_tab == "🏢 Godown Stock":
    st.subheader("🏢 Godown Stock Management")
    
    g_cat = st.radio("Category Chunein", CATEGORIES, horizontal=True, key="g_cat_sel")
    
    # Toggle states for Godown
    st.session_state.setdefault("g_mode", "view") # "view", "add", "edit"
    
    g_col_btn1, g_col_btn2 = st.columns(2)
    if g_col_btn1.button("➕ Naya Item Jorein", type="primary" if st.session_state["g_mode"] != "add" else "secondary"):
        st.session_state["g_mode"] = "add"
        st.rerun()
    if g_col_btn2.button("✏️ Edit / Delete Items", type="primary" if st.session_state["g_mode"] != "edit" else "secondary"):
        st.session_state["g_mode"] = "edit"
        st.rerun()

    filtered_godown = godown_df[godown_df["category"] == g_cat]

    # MODE 1: ADD ITEM
    if st.session_state["g_mode"] == "add":
        st.markdown(f"#### ➕ Add New Godown Item ({g_cat})")
        st.session_state.setdefault("g_add_key", 0)
        ak = st.session_state["g_add_key"]

        g_cat_pool = alld[alld["category"] == g_cat]
        g_sz_opts = sorted({x for x in g_cat_pool["size"] if x}, key=size_key)
        g_cl_opts = sorted({x for x in g_cat_pool["color"] if x}, key=str.lower)

        gc1, gc2, gc3 = st.columns([2, 2, 1.5])
        with gc1:
            g_sz_raw = smart_selectbox("Size", g_sz_opts, "", key=f"g_sz_{ak}")
        with gc2:
            g_cl_raw = smart_selectbox("Color", g_cl_opts, "", key=f"g_cl_{ak}")
        with gc3:
            g_qty_val = st.number_input("Cartons", min_value=0.5, step=0.5, value=None, placeholder="Qty", key=f"g_qt_{ak}")

        g_sz_val = clean_size(g_sz_raw) if g_sz_raw else ""
        g_cl_val = clean_text(g_cl_raw) if g_cl_raw else ""

        if st.button("💾 Save Item", type="primary", disabled=not (g_sz_val and g_cl_val and g_qty_val)):
            existing = db().table("godown_stock").select("*").eq("category", g_cat).eq("size", g_sz_val).eq("color", g_cl_val).execute().data
            if existing:
                new_qty = float(existing[0]["cartons"]) + float(g_qty_val)
                db().table("godown_stock").update({"cartons": new_qty}).eq("id", existing[0]["id"]).execute()
            else:
                db().table("godown_stock").insert({
                    "category": g_cat, "size": g_sz_val, "color": g_cl_val, "cartons": float(g_qty_val)
                }).execute()
            clear_cache()
            st.session_state["g_add_key"] += 1
            st.success("Item saved successfully! 🎉")
            st.rerun()

        if st.button("👁️ View Mode Par Wapas Jayein"):
            st.session_state["g_mode"] = "view"
            st.rerun()

    # MODE 2: EDIT / DELETE ITEMS
    elif st.session_state["g_mode"] == "edit":
        st.markdown(f"#### ✏️ Edit or Delete Godown Stock ({g_cat})")
        if filtered_godown.empty:
            st.info("Koi stock nahi hai.")
        else:
            sorted_g = filtered_godown.sort_values(by=["size_num", "size", "color"])
            for _, row in sorted_g.iterrows():
                r_id = row["id"]
                r_sz = row["size"]
                r_cl = row["color"]
                r_qt = float(row["cartons"])
                
                gr1, gr2, gr3, gr4 = st.columns([2, 2, 1.5, 1.1])
                g_nsz = gr1.text_input("Size", value=r_sz, key=f"gsz_{r_id}")
                g_ncl = gr2.text_input("Color", value=r_cl, key=f"gcl_{r_id}")
                g_nqt = gr3.number_input("Ctn", min_value=0.5, step=0.5, value=r_qt, key=f"gqt_{r_id}")
                
                gb1, gb2 = gr4.columns(2)
                if gb1.button("💾", help="Update", key=f"g_upd_{r_id}"):
                    db().table("godown_stock").update({
                        "size": clean_size(g_nsz), "color": clean_text(g_ncl), "cartons": float(g_nqt)
                    }).eq("id", r_id).execute()
                    clear_cache()
                    st.success("Updated!")
                    st.rerun()
                if gb2.button("🗑️", help="Delete", key=f"g_del_{r_id}"):
                    db().table("godown_stock").delete().eq("id", int(r_id)).execute()
                    clear_cache()
                    st.rerun()

        if st.button("👁️ View Mode Par Wapas Jayein"):
            st.session_state["g_mode"] = "view"
            st.rerun()

    # MODE 3: DEFAULT CLEAN VIEW (Like Stock Search)
    else:
        st.markdown(f"### 📦 Godown Stock: **{g_cat}**")
        if filtered_godown.empty:
            st.info(f"'{g_cat}' category mein godown mein koi stock nahi hai.")
        else:
            # Group by size ascending
            sorted_g = filtered_godown.sort_values(by=["size_num", "size", "color"])
            for size, sg in sorted_g.groupby("size", sort=False):
                tot_sz_ctn = sg["cartons"].sum()
                tot_sz_str = f"{int(tot_sz_ctn)}" if tot_sz_ctn.is_integer( ) else f"{tot_sz_ctn}"
                with st.expander(f"Size: {size} — Total: {tot_sz_str} ctn"):
                    for _, row in sg.iterrows():
                        q_s = f"{int(row['cartons'])}" if float(row['cartons']).is_integer() else f"{row['cartons']}"
                        st.markdown(f'<div class="stock-box"><span class="c-name">{row["color"]}</span><span class="c-qty">{q_s} ctn</span></div>', unsafe_allow_html=True)

# ---------- TAB 3: HOME ----------
elif selected_tab == "🏠 Home":
    tc1, tc2 = st.columns(2)
    manage = tc1.toggle("🛠 Priority Controls", key="manage")
    only_pri = tc2.toggle("⭐ Sirf Priority", value=True, key="only_pri")

    q = st.text_input("🔍 Search", placeholder="Size, color ya vendor search karein...", label_visibility="collapsed")

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
            tot_c = dc['cartons'].sum()
            tot_c_str = f"{int(tot_c)}" if tot_c.is_integer() else f"{tot_c}"
            st.success(f"{cat} Total: {tot_c_str} cartons")
    else:
        for cat, ctab in zip(cats, st.tabs(cats)):
            with ctab:
                dc = d[d["category"] == cat]
                if dc.empty:
                    st.info("Priority wala koi maal nahi." if only_pri else "Is category mein koi maal on the way nahi.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                tot_c = dc['cartons'].sum()
                tot_c_str = f"{int(tot_c)}" if tot_c.is_integer() else f"{tot_c}"
                st.success(f"{cat} Total: {tot_c_str} cartons")

# ---------- TAB 4: VENDOR BILL VIEWER ----------
elif selected_tab == "🧾 Vendor Bill":
    st.subheader("Vendor-Wise Bills")
    all_vendors = sorted([v for v in otw["vendor"].unique() if v])
    selected_v = st.selectbox("Vendor Chunein", all_vendors, placeholder="Vendor select karein", key="v_bill_sel")

    if selected_v:
        v_otw = otw[otw["vendor"] == selected_v]
        bill_ids = v_otw["bill_id"].unique()

        st.markdown(f"### 📋 Bills for: **{selected_v}**")

        for idx, b_id in enumerate(bill_ids):
            b_data = sort_df(v_otw[v_otw["bill_id"] == b_id])
            b_date = b_data["ordered_on"].iloc[0]
            b_tot = b_data["cartons"].sum()
            b_tot_str = f"{int(b_tot)}" if b_tot.is_integer() else f"{b_tot}"

            with st.expander(f"📦 Bill #{idx+1} — 📅 {b_date} — Total: {b_tot_str} cartons"):
                edit_state_key = f"edit_mode_{b_id}"
                if edit_state_key not in st.session_state:
                    st.session_state[edit_state_key] = False

                if not st.session_state[edit_state_key]:
                    display_df = b_data[["category", "size", "color", "cartons", "ordered_on"]].copy()
                    display_df["cartons"] = display_df["cartons"].apply(lambda x: f"{int(x)}" if float(x).is_integer() else f"{x}")
                    st.dataframe(display_df, hide_index=True, use_container_width=True)

                    v_rcv_c1, v_rcv_c2 = st.columns(2)
                    if v_rcv_c1.button("✅ Received Mark Karein", key=f"recv_safe_{b_id}", type="primary"):
                        db().table("orders").update({"status": "received", "received_on": str(date.today())}).eq("bill_id", b_id).execute()
                        clear_cache()
                        st.session_state["msg"] = f"Bill #{idx+1} received ho gaya! ✅"
                        st.rerun()
                    if v_rcv_c2.button("✏️ Edit / Add Items", key=f"tgl_{b_id}"):
                        st.session_state[edit_state_key] = True
                        st.rerun()
                else:
                    st.markdown("#### ✏️ Bill Edit & Add Items:")
                    ed_meta_c1, ed_meta_c2 = st.columns([3, 2])
                    edit_bill_vendor = ed_meta_c1.text_input("Vendor Name", value=selected_v, key=f"bv_{b_id}")
                    
                    parsed_b_date = date.today()
                    try:
                        if b_date: parsed_b_date = date.fromisoformat(b_date)
                    except: pass
                    edit_bill_date = ed_meta_c2.date_input("Order Date", value=parsed_b_date, key=f"bd_{b_id}")
                    
                    if st.button("💾 Save Bill Info", key=f"save_meta_{b_id}"):
                        db().table("orders").update({"vendor": clean_text(edit_bill_vendor), "ordered_on": str(edit_bill_date)}).eq("bill_id", b_id).execute()
                        clear_cache()
                        st.success("Updated!")
                        st.rerun()

                    st.markdown("---")
                    for _, row in b_data.iterrows():
                        r_id = row["id"]
                        r_sz, r_cl, r_qt = row["size"], row["color"], float(row["cartons"])
                        
                        ed1, ed2, ed3, ed4 = st.columns([2, 2, 1.5, 1.1])
                        nsz = ed1.text_input("Size", value=r_sz, key=f"sz_{r_id}")
                        ncl = ed2.text_input("Color", value=r_cl, key=f"cl_{r_id}")
                        nqt = ed3.number_input("Ctn", min_value=0.5, step=0.5, value=r_qt, key=f"qt_{r_id}")
                        
                        bc1, bc2 = ed4.columns(2)
                        if bc1.button("💾", key=f"sv_{r_id}"):
                            db().table("orders").update({"size": clean_size(nsz), "color": clean_text(ncl), "cartons": float(nqt)}).eq("id", r_id).execute()
                            clear_cache()
                            st.rerun()
                        if bc2.button("🗑️", key=f"dl_{r_id}"):
                            delete_row(r_id)
                            st.rerun()

                    st.markdown("---")
                    add_cat = st.radio("Category", CATEGORIES, horizontal=True, key=f"ac_{b_id}")
                    cat_sub = alld[alld["category"] == add_cat]
                    all_sz_opts = sorted({s for s in cat_sub["size"] if s}, key=size_key)
                    all_cl_opts = sorted({c for c in cat_sub["color"] if c}, key=str.lower)
                    
                    ex1, ex2, ex3 = st.columns([2, 2, 1.5])
                    new_sz = smart_selectbox("Size", all_sz_opts, "", key=f"esz_{b_id}")
                    new_cl = smart_selectbox("Color", all_cl_opts, "", key=f"ecl_{b_id}")
                    new_qt = ex3.number_input("Cartons", min_value=0.5, step=0.5, value=1.0, key=f"eqt_{b_id}")
                    new_pr = st.checkbox("⭐ Priority", key=f"epr_{b_id}")
                    
                    if st.button("➕ Add Item to Bill", key=f"btn_add_{b_id}", type="primary"):
                        s_c = clean_size(new_sz) if new_sz else ""
                        c_c = clean_text(new_cl) if new_cl else ""
                        if s_c and c_c:
                            db().table("orders").insert({
                                "bill_id": b_id, "vendor": clean_text(edit_bill_vendor), "category": add_cat,
                                "size": s_c, "color": c_c, "cartons": float(new_qt), "priority": bool(new_pr),
                                "ordered_on": str(edit_bill_date), "status": "on_the_way"
                            }).execute()
                            clear_cache()
                            st.success("Added! 🎉")
                            st.rerun()
                        else:
                            st.warning("Size aur Color select karein.")

                    if st.button("👁️ View Mode Par Wapas Jayein", key=f"cls_{b_id}"):
                        st.session_state[edit_state_key] = False
                        st.rerun()

# ---------- TAB 5: NAYA BILL (Strictly Category-Separated Memory) ----------
elif selected_tab == "➕ Naya Bill":
    ss = st.session_state
    if "draft" not in ss:
        ss["draft"], _ = load_draft()
    dr = ss["draft"]
    ss.setdefault("ak", 0)

    dr.setdefault("lines", [])
    dr.setdefault("order_date", str(date.today()))

    col_vd1, col_vd2 = st.columns([3, 2])
    raw_vendors = {v for v in alld["vendor"] if v}
    vend_opts = sorted(raw_vendors, key=str.lower)
    picked_v = smart_selectbox("Vendor Name", vend_opts, dr.get("vendor", ""), key=f"v_sel_{ss['ak']}")
    vendor = clean_text(picked_v) if picked_v else ""
    if vendor != dr.get("vendor", ""):
        dr["vendor"] = vendor
        save_draft()

    parsed_date = date.today()
    try:
        if dr.get("order_date"): parsed_date = date.fromisoformat(dr["order_date"])
    except: pass
    selected_date = col_vd2.date_input("Order Date", value=parsed_date, key=f"odate_{ss['ak']}")
    if str(selected_date) != dr.get("order_date"):
        dr["order_date"] = str(selected_date)
        save_draft()

    cat = st.radio("Category", CATEGORIES, index=CATEGORIES.index(dr["category"]) if dr.get("category") in CATEGORIES else 0, horizontal=True, key="cart_cat")
    if cat != dr.get("category"):
        dr["category"] = cat
        save_draft()

    # STRICT CATEGORY ISOLATION FOR SIZES & COLORS
    cat_pool = alld[alld["category"] == cat]
    sheet_sizes = {clean_size(l["size"]) for l in dr["lines"] if l.get("category") == cat}
    sheet_colors = {clean_text(l["color"]) for l in dr["lines"] if l.get("category") == cat}

    size_opts = sorted(({x for x in cat_pool["size"] if x} | sheet_sizes), key=size_key)
    color_opts = sorted(({x for x in cat_pool["color"] if x} | sheet_colors), key=str.lower)

    st.markdown("##### ➕ Item Add Karein")
    in_c1, in_c2, in_c3 = st.columns([2, 2, 1.5])
    sz_raw = smart_selectbox("Size", size_opts, "", key=f"c_sz_{ss['ak']}")
    cl_raw = smart_selectbox("Color", color_opts, "", key=f"c_cl_{ss['ak']}")
    cartons_val = st.number_input("Cartons", min_value=0.5, step=0.5, value=None, placeholder="Qty", key=f"c_qty_{ss['ak']}")

    sz_val = clean_size(sz_raw) if sz_raw else ""
    cl_val = clean_text(cl_raw) if cl_raw else ""

    add_c1, add_c2 = st.columns([1.5, 3])
    pri_val = add_c1.checkbox("⭐ Priority", key=f"c_pri_{ss['ak']}")
    if add_c2.button("➕ Bill mein jorein", type="primary", disabled=not (sz_val and cl_val and cartons_val)):
        dr["lines"].append({"category": cat, "size": sz_val, "color": cl_val, "cartons": float(cartons_val), "priority": bool(pri_val)})
        save_draft()
        ss["ak"] += 1
        st.rerun()

    lines = dr.get("lines", [])
    if lines:
        st.markdown(f"##### 🧾 Current Bill — **{vendor or '⚠️ Vendor select nahi kiya'}**")
        for i, l in enumerate(lines):
            star_txt = " ⭐" if l["priority"] else ""
            c_qty_str = f"{int(l['cartons'])}" if l['cartons'].is_integer() else f"{l['cartons']}"
            
            rc1, rc2, rc3 = st.columns([5.2, 0.9, 0.9])
            rc1.markdown(f'<div class="cart-row"><b>{i+1}.</b> [{l["category"]}] <b>{l["size"]}</b> — {l["color"]} — <b>{c_qty_str} ctn</b>{star_txt}</div>', unsafe_allow_html=True)
            
            with rc2.popover("✏️"):
                ed_sz = st.text_input("Size", value=l["size"], key=f"dsz_{i}")
                ed_cl = st.text_input("Color", value=l["color"], key=f"dcl_{i}")
                ed_qt = st.number_input("Cartons", min_value=0.5, step=0.5, value=float(l["cartons"]), key=f"dqt_{i}")
                ed_pr = st.checkbox("Priority", value=l["priority"], key=f"dpr_{i}")
                if st.button("Save", key=f"dsv_{i}"):
                    lines[i] = {"category": l["category"], "size": clean_size(ed_sz), "color": clean_text(ed_cl), "cartons": float(ed_qt), "priority": bool(ed_pr)}
                    save_draft()
                    st.rerun()
            if rc3.button("🗑️", key=f"ddl_{i}_{ss['ak']}"):
                lines.pop(i)
                save_draft()
                ss["ak"] += 1
                st.rerun()

        if st.button("💾 Poora Bill Save Karein", type="primary", disabled=not vendor):
            unique_id = f"bill_{int(time.time()*1000)}"
            rows = [{"bill_id": unique_id, "vendor": vendor, "category": l["category"], "size": l["size"], "color": l["color"], "cartons": float(l["cartons"]), "priority": l["priority"], "ordered_on": dr["order_date"]} for l in lines]
            db().table("orders").insert(rows).execute()
            clear_cache()
            dr["lines"] = []
            dr["vendor"] = ""
            save_draft()
            ss["ak"] += 1
            st.session_state["msg"] = f"{vendor} ka bill save ho gaya! 🎉"
            st.rerun()

        if st.button("🧹 Clear Cart"):
            dr["lines"] = []
            save_draft()
            ss["ak"] += 1
            st.rerun()

# ---------- TAB 6: HISTORY ----------
elif selected_tab == "📜 History":
    st.subheader("Receive ho chuka maal")
    st.session_state.setdefault("hk", 0)
    hk = st.session_state["hk"]
    rec = alld[alld["status"] == "received"]
    f1, f2 = st.columns(2)
    fc = f1.selectbox("Category", ["Sab"] + CATEGORIES, key="h_cat")
    hq = f2.text_input("🔍 Search History", key="h_q")
    if fc != "Sab": rec = rec[rec["category"] == fc]
    if hq.strip(): rec = search(rec, hq)
    rec = sort_df(rec)

    if rec.empty:
        st.info("Koi received maal nahi.")
    else:
        view = rec[["id", "category", "size", "color", "vendor", "cartons", "received_on"]].copy()
        view.insert(0, "Select", False)
        edited = st.data_editor(view, hide_index=True, key=f"hist_{hk}_{fc}_{hq}", use_container_width=True, column_config={"id": None, "Select": st.column_config.CheckboxColumn("✔")}, disabled=[c for c in view.columns if c != "Select"])
        ids = [int(x) for x in edited.loc[edited["Select"], "id"]]
        if st.button("↩️ Wapas On the Way", disabled=not ids):
            db().table("orders").update({"status": "on_the_way", "received_on": None}).in_("id", ids).eq("status", "received").execute()
            clear_cache()
            st.session_state["hk"] += 1
            st.rerun()