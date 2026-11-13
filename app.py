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
NO_VENDOR = "(vendor nahi likha)"
CAT_ORDER = {c: i for i, c in enumerate(CATEGORIES)}
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="wide")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {
    padding-top: 0.6rem;
    padding-bottom: 5rem;
    max-width: 820px;
    margin: auto;
}

h1 {font-size: 1.35rem !important; font-weight: 700; color: #0f172a; margin-bottom: 0.4rem;}
h3 {font-size: 1.08rem !important; font-weight: 600; color: #1e293b;}
h5 {font-size: 0.92rem !important; font-weight: 600; color: #334155; margin-top: .5rem;}

.stButton > button, .stDownloadButton > button {
    min-height: 2.7rem;
    border-radius: 10px;
    font-weight: 600;
    width: 100%;
    border: 1px solid #cbd5e1;
    background-color: #ffffff;
    color: #1e293b;
    padding: 0.3rem 0.6rem;
    transition: all 0.15s ease;
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
    border-radius: 10px !important;
    min-height: 2.7rem !important;
}

[data-testid="stExpander"] details {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background: #ffffff;
    margin-bottom: 0.45rem;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
[data-testid="stExpander"] summary {
    padding: .7rem .9rem;
    font-weight: 600;
    color: #0f172a;
}

button[data-baseweb="tab"] {
    font-weight: 600;
    padding: .5rem 0.75rem;
    font-size: 0.88rem;
}

.stock-box {
    border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc;
    padding: 0.75rem 1rem; margin-bottom: 0.5rem; display: flex;
    justify-content: space-between; align-items: center;
}
.stock-box .c-name {font-weight: 600; color: #1e293b; font-size: 1rem;}
.stock-box .c-qty {font-weight: 700; color: #0f172a; font-size: 1rem; background: #e2e8f0; padding: 0.2rem 0.7rem; border-radius: 8px;}

.cart-row {
    border: 1px solid #e2e8f0;
    background: #f8fafc;
    border-radius: 10px;
    padding: 0.55rem 0.8rem;
    margin-bottom: 0.35rem;
    font-size: 0.92rem;
    color: #0f172a;
}
.home-line {
    padding: 0.35rem 0;
    font-size: 0.93rem;
    color: #1e293b;
}

@media (max-width: 640px) {
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.35rem !important;
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


# ---------- Database ----------
@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


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


def update_rows(ids, fields):
    db().table("orders").update(fields).in_("id", [int(i) for i in ids]).execute()


def delete_row(row_id):
    db().table("orders").delete().eq("id", int(row_id)).execute()


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
        pass


try:
    alld = load_all()
except Exception as e:
    st.error("Database connection error. Check Supabase project.")
    st.caption(str(e))
    st.stop()

otw = alld[alld["status"] == "on_the_way"]


# ---------- Helpers (Ascending Size Sorting) ----------
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


# ======================= SIDEBAR (Master Data & Export) =======================
with st.sidebar:
    st.markdown("### ⚙️ Master Data & Export")
    
    # Sort unreceived export by size ascending
    unrec_df = otw.sort_values(by=["size_num", "size"])[["ordered_on", "size", "color", "cartons", "category"]].copy()
    unrec_df.columns = ["Date", "Size", "Color", "Carton Quantity", "Category"]
    csv_data = unrec_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "📥 Download Unreceived Excel (CSV)",
        csv_data,
        file_name=f"unreceived_stock_{date.today()}.csv",
        mime="text/csv",
        help="Export all unreceived items without vendor names"
    )
    
    st.markdown("---")
    st.markdown("#### 🗑️ Dropdown Cleanup")
    st.caption("Ghalat save hone wale Vendor, Size ya Color ko yahan se hata sakte hain.")
    
    if "draft" not in st.session_state:
        st.session_state["draft"], _ = load_draft()
    dr_side = st.session_state["draft"]
    
    all_vs = sorted({v for v in alld["vendor"] if v} - set(dr_side.get("del_vendors", [])))
    del_v_pick = st.selectbox("Vendor Hatayen", all_vs, index=None, placeholder="Vendor chunein...", key="side_del_v")
    if st.button("Vendor Delete Karein", disabled=not del_v_pick):
        dr_side.setdefault("del_vendors", []).append(del_v_pick)
        save_draft()
        st.success(f"Vendor '{del_v_pick}' hata diya gaya!")
        st.rerun()

    all_szs = sorted({s for s in alld["size"] if s}, key=size_key)
    del_sz_pick = st.selectbox("Size Hatayen", all_szs, index=None, placeholder="Size chunein...", key="side_del_sz")
    if st.button("Size Delete Karein", disabled=not del_sz_pick):
        for c_item in CATEGORIES:
            dr_side.setdefault("del_sizes", {}).setdefault(c_item, []).append(del_sz_pick)
        save_draft()
        st.success(f"Size '{del_sz_pick}' hata diya gaya!")
        st.rerun()

    all_cls = sorted({c for c in alld["color"] if c}, key=str.lower)
    del_cl_pick = st.selectbox("Color Hatayen", all_cls, index=None, placeholder="Color chunein...", key="side_del_cl")
    if st.button("Color Delete Karein", disabled=not del_cl_pick):
        for c_item in CATEGORIES:
            dr_side.setdefault("del_colors", {}).setdefault(c_item, []).append(del_cl_pick)
        save_draft()
        st.success(f"Color '{del_cl_pick}' hata diya gaya!")
        st.rerun()


# ======================= PAGE HEADER & TOP RIGHT MENU BUTTON =======================
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
    st.caption("Master data cleanup ke liye sidebar check karein.")

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

TAB_LIST = ["🔍 Stock Search", "🏠 Home", "🧾 Vendor Bill", "➕ Naya Bill", "📜 History"]
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = TAB_LIST[0]

selected_tab = st.radio("Navigation", TAB_LIST, index=TAB_LIST.index(st.session_state["active_tab"]), horizontal=True, label_visibility="collapsed")
st.session_state["active_tab"] = selected_tab
st.markdown("---")

# ---------- TAB 1: STOCK SEARCH ----------
if selected_tab == "🔍 Stock Search":
    st.subheader("Category & Size Filter")
    s_cat = st.radio("Category Chunein", CATEGORIES, horizontal=True, key="search_cat")
    cat_otw = otw[otw["category"] == s_cat]

    if cat_otw.empty:
        st.info(f"'{s_cat}' category mein koi on-the-way stock nahi hai.")
    else:
        # Ascending sort for sizes
        available_sizes = sorted(cat_otw["size"].unique(), key=size_key)
        s_size = st.selectbox("Size Chunein", available_sizes, placeholder="Size select karein...", key="search_size")

        if s_size:
            size_data = cat_otw[cat_otw["size"] == s_size].copy()
            color_summary = size_data.groupby("color")["cartons"].sum().reset_index()
            color_summary = color_summary.sort_values(by="cartons", ascending=False)

            st.markdown(f"### 📊 Size: **{s_size}** ({s_cat})")
            if color_summary.empty:
                st.info("Is size mein koi color nahi mila.")
            else:
                for _, row in color_summary.iterrows():
                    c_col = row["color"]
                    c_qty = row["cartons"]
                    c_qty_str = f"{int(c_qty)}" if c_qty.is_integer() else f"{c_qty}"
                    st.markdown(
                        f'<div class="stock-box"><span class="c-name">{c_col}</span><span class="c-qty">{c_qty_str} cartons</span></div>',
                        unsafe_allow_html=True
                    )

# ---------- TAB 2: HOME ----------
elif selected_tab == "🏠 Home":
    tc1, tc2 = st.columns(2)
    manage = tc1.toggle("🛠 Priority Controls", key="manage")
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
            tot_c = dc['cartons'].sum()
            tot_c_str = f"{int(tot_c)}" if tot_c.is_integer() else f"{tot_c}"
            st.success(f"{cat} Total: {tot_c_str} cartons")
    else:
        for cat, ctab in zip(cats, st.tabs(cats)):
            with ctab:
                dc = d[d["category"] == cat]
                if dc.empty:
                    st.info("Priority wala koi maal nahi. Sab dekhne ke liye ⭐ switch band karein."
                            if only_pri else "Is category mein koi maal on the way nahi.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                tot_c = dc['cartons'].sum()
                tot_c_str = f"{int(tot_c)}" if tot_c.is_integer() else f"{tot_c}"
                st.success(f"{cat} Total: {tot_c_str} cartons")

# ---------- TAB 3: VENDOR BILL VIEWER (Safe Read-Only View by Default) ----------
elif selected_tab == "🧾 Vendor Bill":
    st.subheader("Vendor-Wise Bills")
    all_vendors = sorted([v for v in otw["vendor"].unique() if v])
    selected_v = st.selectbox("Vendor Chunein", all_vendors, placeholder="Vendor select karein", key="v_bill_sel")

    if selected_v:
        v_otw = otw[otw["vendor"] == selected_v]
        bill_ids = v_otw["bill_id"].unique()

        st.markdown(f"### 📋 Bills for: **{selected_v}**")

        for idx, b_id in enumerate(bill_ids):
            # Sort items inside bill by size ascending
            b_data = sort_df(v_otw[v_otw["bill_id"] == b_id])
            b_date = b_data["ordered_on"].iloc[0]
            b_tot = b_data["cartons"].sum()
            b_tot_str = f"{int(b_tot)}" if b_tot.is_integer() else f"{b_tot}"

            with st.expander(f"📦 Bill #{idx+1} — 📅 {b_date} — Total: {b_tot_str} cartons"):
                
                # Check if edit mode is toggled for this specific bill in session state
                edit_state_key = f"edit_mode_{b_id}"
                if edit_state_key not in st.session_state:
                    st.session_state[edit_state_key] = False

                # DEFAULT VIEW: Clean Read-Only Table (No accidental edits)
                if not st.session_state[edit_state_key]:
                    display_df = b_data[["category", "size", "color", "cartons", "ordered_on"]].copy()
                    display_df["cartons"] = display_df["cartons"].apply(lambda x: f"{int(x)}" if float(x).is_integer() else f"{x}")
                    st.dataframe(display_df, hide_index=True, use_container_width=True)

                    v_rcv_c1, v_rcv_c2 = st.columns(2)
                    if v_rcv_c1.button("✅ Ye Poora Bill Received Karein", key=f"recv_bill_safe_{b_id}", type="primary"):
                        db().table("orders").update({"status": "received", "received_on": str(date.today())}).eq("bill_id", b_id).execute()
                        st.session_state["msg"] = f"Bill #{idx+1} ({selected_v}) received mark ho gaya! ✅"
                        st.rerun()

                    if v_rcv_c2.button("✏️ Bill Edit / Add Items", key=f"toggle_edit_{b_id}"):
                        st.session_state[edit_state_key] = True
                        st.rerun()

                # EDIT MODE VIEW (Opened only when edit button is clicked)
                else:
                    st.markdown("#### ✏️ Bill Edit & Add Items:")
                    
                    ed_meta_c1, ed_meta_c2 = st.columns([3, 2])
                    edit_bill_vendor = ed_meta_c1.text_input("Vendor Name", value=selected_v, key=f"bill_v_edit_{b_id}")
                    
                    parsed_b_date = date.today()
                    try:
                        if b_date:
                            parsed_b_date = date.fromisoformat(b_date)
                    except Exception:
                        pass
                    edit_bill_date = ed_meta_c2.date_input("Order Date", value=parsed_b_date, key=f"bill_d_edit_{b_id}")
                    
                    if st.button("💾 Bill Info Save Karein", key=f"upd_bill_meta_{b_id}"):
                        db().table("orders").update({
                            "vendor": clean_text(edit_bill_vendor),
                            "ordered_on": str(edit_bill_date)
                        }).eq("bill_id", b_id).execute()
                        st.success("Bill info updated! ✅")
                        st.rerun()

                    st.markdown("---")
                    st.markdown("#### Existing Items (Edit / Delete):")
                    
                    for _, row in b_data.iterrows():
                        r_id = row["id"]
                        r_cat = row["category"]
                        r_sz = row["size"]
                        r_cl = row["color"]
                        r_qt = float(row["cartons"])
                        
                        row_ed1, row_ed2, row_ed3, row_ed4 = st.columns([2, 2, 1.5, 1.1])
                        new_sz = row_ed1.text_input("Size", value=r_sz, key=f"sz_inline_{r_id}")
                        new_cl = row_ed2.text_input("Color", value=r_cl, key=f"cl_inline_{r_id}")
                        new_qt = row_ed3.number_input("Ctn", min_value=0.5, step=0.5, value=r_qt, key=f"qt_inline_{r_id}")
                        
                        btn_c1, btn_c2 = row_ed4.columns(2)
                        if btn_c1.button("💾", help="Save changes", key=f"save_inline_{r_id}"):
                            db().table("orders").update({
                                "size": clean_size(new_sz),
                                "color": clean_text(new_cl),
                                "cartons": float(new_qt)
                            }).eq("id", r_id).execute()
                            st.success("Updated!")
                            st.rerun()
                        if btn_c2.button("🗑️", help="Delete item", key=f"del_inline_{r_id}"):
                            delete_row(r_id)
                            st.rerun()

                    st.markdown("---")
                    st.markdown("#### ➕ Is Bill mein Naya Item Jorein:")
                    
                    add_cat = st.radio("Category", CATEGORIES, horizontal=True, key=f"exp_add_cat_{b_id}")
                    
                    # Ascending sorted options
                    all_sz_opts = sorted({s for s in alld["size"] if s}, key=size_key)
                    all_cl_opts = sorted({c for c in alld["color"] if c}, key=str.lower)
                    
                    ex_c1, ex_c2, ex_c3 = st.columns([2, 2, 1.5])
                    with ex_c1:
                        new_item_sz = smart_selectbox("Size", all_sz_opts, "", key=f"exp_sz_{b_id}")
                    with ex_c2:
                        new_item_cl = smart_selectbox("Color", all_cl_opts, "", key=f"exp_cl_{b_id}")
                    with ex_c3:
                        new_item_qt = st.number_input("Cartons", min_value=0.5, step=0.5, value=1.0, key=f"exp_qt_{b_id}")
                    
                    new_item_pr = st.checkbox("⭐ Priority", key=f"exp_pr_{b_id}")
                    
                    if st.button("➕ Bill mein Item Add Karein", key=f"btn_add_to_bill_{b_id}", type="primary"):
                        s_clean = clean_size(new_item_sz) if new_item_sz else ""
                        c_clean = clean_text(new_item_cl) if new_item_cl else ""
                        if s_clean and c_clean:
                            db().table("orders").insert({
                                "bill_id": b_id,
                                "vendor": clean_text(edit_bill_vendor),
                                "category": add_cat,
                                "size": s_clean,
                                "color": c_clean,
                                "cartons": float(new_item_qt),
                                "priority": bool(new_item_pr),
                                "ordered_on": str(edit_bill_date),
                                "status": "on_the_way"
                            }).execute()
                            st.success("Naya item bill mein add ho gaya! 🎉")
                            st.rerun()
                        else:
                            st.warning("Size aur Color select karna ya likhna lazmi hai.")

                    st.markdown("---")
                    if st.button("👁️ View Mode Par Wapas Jayein", key=f"close_edit_{b_id}"):
                        st.session_state[edit_state_key] = False
                        st.rerun()

# ---------- TAB 4: NAYA BILL ----------
elif selected_tab == "➕ Naya Bill":
    ss = st.session_state
    if "draft" not in ss:
        ss["draft"], _ = load_draft()
    dr = ss["draft"]
    ss.setdefault("ak", 0)

    if not isinstance(dr.get("del_sizes"), dict):
        dr["del_sizes"] = {}
    if not isinstance(dr.get("del_colors"), dict):
        dr["del_colors"] = {}
    if not isinstance(dr.get("del_vendors"), list):
        dr["del_vendors"] = []
    dr.setdefault("lines", [])
    dr.setdefault("order_date", str(date.today()))

    st.caption("🔒 Auto-save on hai — Naya bill banayein, har baar naya Bill # assign hoga.")

    col_vd1, col_vd2 = st.columns([3, 2])
    raw_vendors = {v for v in alld["vendor"] if v} - set(dr["del_vendors"])
    vend_opts = sorted(raw_vendors, key=str.lower)
    with col_vd1:
        picked_v = smart_selectbox("Vendor Name", vend_opts, dr.get("vendor", ""), key=f"v_sel_{ss['ak']}")
    vendor = clean_text(picked_v) if picked_v else ""
    if vendor != dr.get("vendor", ""):
        dr["vendor"] = vendor
        if vendor in dr["del_vendors"]:
            dr["del_vendors"].remove(vendor)
        save_draft()

    parsed_date = date.today()
    try:
        if dr.get("order_date"):
            parsed_date = date.fromisoformat(dr["order_date"])
    except Exception:
        pass

    selected_date = col_vd2.date_input("Order Date", value=parsed_date, key=f"order_date_input_{ss['ak']}")
    if str(selected_date) != dr.get("order_date"):
        dr["order_date"] = str(selected_date)
        save_draft()

    cat = st.radio(
        "Category", CATEGORIES,
        index=CATEGORIES.index(dr["category"]) if dr.get("category") in CATEGORIES else 0,
        horizontal=True, key="cart_cat"
    )
    if cat != dr.get("category"):
        dr["category"] = cat
        save_draft()

    cat_del_sizes = dr["del_sizes"].get(cat, [])
    cat_del_colors = dr["del_colors"].get(cat, [])

    # Ascending sort for size options
    size_opts = sorted(
        ({x for x in alld["size"] if x}) - set(cat_del_sizes),
        key=size_key
    )
    color_opts = sorted(
        ({x for x in alld["color"] if x}) - set(cat_del_colors),
        key=str.lower
    )

    st.markdown("##### ➕ Item Add Karein")
    in_c1, in_c2, in_c3 = st.columns([2, 2, 1.5])
    with in_c1:
        sz_raw = smart_selectbox("Size", size_opts, "", key=f"c_sz_{ss['ak']}")
    with in_c2:
        cl_raw = smart_selectbox("Color", color_opts, "", key=f"c_cl_{ss['ak']}")
    with in_c3:
        cartons_val = st.number_input("Cartons", min_value=0.5, step=0.5, value=None, placeholder="Qty", key=f"c_qty_{ss['ak']}")

    sz_val = clean_size(sz_raw) if sz_raw else ""
    cl_val = clean_text(cl_raw) if cl_raw else ""

    add_c1, add_c2 = st.columns([1.5, 3])
    pri_val = add_c1.checkbox("⭐ Priority", key=f"c_pri_{ss['ak']}")
    if add_c2.button("➕ Bill mein jorein", type="primary", disabled=not (sz_val and cl_val and cartons_val)):
        dr["lines"].append({
            "category": cat,
            "size": sz_val,
            "color": cl_val,
            "cartons": float(cartons_val),
            "priority": bool(pri_val)
        })
        save_draft()
        ss["ak"] += 1
        st.rerun()

    lines = dr.get("lines", [])
    if lines:
        st.markdown(f"##### 🧾 Current Bill — **{vendor or '⚠️ Vendor select nahi kiya'}** (📅 {dr['order_date']})")

        for i, l in enumerate(lines):
            star_txt = " ⭐" if l["priority"] else ""
            c_qty_str = f"{int(l['cartons'])}" if l['cartons'].is_integer() else f"{l['cartons']}"
            
            row_c1, row_c2, row_c3 = st.columns([5.2, 0.9, 0.9])
            row_c1.markdown(
                f'<div class="cart-row"><b>{i+1}.</b> [{l["category"]}] <b>{l["size"]}</b> — {l["color"]} — <b>{c_qty_str} ctn</b>{star_txt}</div>',
                unsafe_allow_html=True
            )
            
            with row_c2.popover("✏️"):
                ed_sz = st.text_input("Size", value=l["size"], key=f"draft_ed_sz_{i}")
                ed_cl = st.text_input("Color", value=l["color"], key=f"draft_ed_cl_{i}")
                ed_qt = st.number_input("Cartons", min_value=0.5, step=0.5, value=float(l["cartons"]), key=f"draft_ed_qt_{i}")
                ed_pr = st.checkbox("Priority", value=l["priority"], key=f"draft_ed_pr_{i}")
                if st.button("Save Line", key=f"draft_save_line_{i}"):
                    lines[i] = {
                        "category": l["category"],
                        "size": clean_size(ed_sz),
                        "color": clean_text(ed_cl),
                        "cartons": float(ed_qt),
                        "priority": bool(ed_pr)
                    }
                    save_draft()
                    st.success("Line updated!")
                    st.rerun()

            if row_c3.button("🗑️", help="Is item ko hatayen", key=f"del_cart_item_{i}_{ss['ak']}"):
                lines.pop(i)
                save_draft()
                ss["ak"] += 1
                st.rerun()

        total_cartons = sum(l["cartons"] for l in lines)
        tot_c_str = f"{int(total_cartons)}" if total_cartons.is_integer() else f"{total_cartons}"
        st.markdown(f"**Total Cartons: {tot_c_str} • Total Items: {len(lines)}**")

        sv_c1, sv_c2 = st.columns([3, 1])
        if sv_c1.button("💾 Poora Bill Save Karein", type="primary", disabled=not vendor):
            unique_bill_id = f"bill_{int(time.time()*1000)}"
            rows_to_insert = [
                {
                    "bill_id": unique_bill_id,
                    "vendor": vendor,
                    "category": l["category"],
                    "size": l["size"],
                    "color": l["color"],
                    "cartons": float(l["cartons"]),
                    "priority": l["priority"],
                    "ordered_on": dr["order_date"]
                }
                for l in lines
            ]
            try:
                db().table("orders").insert(rows_to_insert).execute()
            except Exception as e:
                st.error("Save nahi ho saka.")
                st.caption(str(e))
                st.stop()

            dr["lines"] = []
            dr["vendor"] = ""
            save_draft()
            ss["ak"] += 1
            st.cache_resource.clear()
            st.session_state["msg"] = f"{vendor} ka naya bill save ho gaya! 🎉"
            st.rerun()

        if sv_c2.button("🧹 Clear"):
            dr["lines"] = []
            save_draft()
            ss["ak"] += 1
            st.rerun()

        if not vendor:
            st.caption("⚠️ Save karne se pehle upar Vendor select karna lazmi hai.")

# ---------- TAB 5: HISTORY ----------
elif selected_tab == "📜 History":
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
            view, hide_index=True, key=f"hist_{hk}_{fc}_{hq}", use_container_width=True,
            column_config={"id": None, "Select": st.column_config.CheckboxColumn("✔")},
            disabled=[c for c in view.columns if c != "Select"],
        )
        ids = [int(x) for x in edited.loc[edited["Select"], "id"]]
        tot_rcv_c = rec.loc[rec["id"].isin(ids), 'cartons'].sum() if ids else rec['cartons'].sum()
        tot_rcv_str = f"{int(tot_rcv_c)}" if tot_rcv_c.is_integer() else f"{tot_rcv_c}"
        st.caption(f"{len(ids)} selected • Total cartons: {tot_rcv_str}")
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