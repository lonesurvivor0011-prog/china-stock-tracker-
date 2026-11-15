import copy
import hashlib
import html
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
NAV = ["🔍 Stock Search", "🏢 Godown", "🏠 Home", "🧾 Vendor Bill", "➕ Naya Bill", "📜 History"]
# ========================================================

st.set_page_config(page_title="Stock On The Way", page_icon="📦", layout="centered")

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: .6rem; padding-bottom: 5rem; max-width: 820px;}
h1 {font-size: 1.3rem !important; font-weight: 700; margin-bottom: .2rem;}
h3 {font-size: 1.05rem !important; font-weight: 700;}
h5 {font-size: .92rem !important; font-weight: 700; margin-top: .5rem;}

.stButton > button, .stDownloadButton > button {
    min-height: 2.6rem; border-radius: 10px; font-weight: 600; width: 100%;
    border: 1px solid rgba(128,128,128,.35); padding: .25rem .5rem;}
button[kind="primary"] {
    background-color: #0f766e !important; border: none !important; color: #fff !important;}
button[kind="primary"]:hover {background-color: #115e59 !important;}
button[kind="primary"]:disabled {opacity: .45;}

[data-baseweb="select"] > div, div[data-baseweb="input"] input {
    border-radius: 10px !important; min-height: 2.6rem !important;}

[data-testid="stExpander"] details {
    border: 1px solid rgba(128,128,128,.30); border-radius: 12px; margin-bottom: .35rem;}
[data-testid="stExpander"] summary {padding: .65rem .85rem; font-weight: 600;}
button[data-baseweb="tab"] {font-weight: 600; padding: .45rem .7rem; font-size: .85rem;}
div[role="radiogroup"] {gap: .3rem .9rem;}

.stock-box, .cart-row {
    border: 1px solid rgba(128,128,128,.28); background: rgba(128,128,128,.08);
    border-radius: 10px; padding: .55rem .8rem; margin-bottom: .35rem; font-size: .92rem;}
.stock-box {display: flex; justify-content: space-between; align-items: center; gap: .5rem;}
.stock-box .c-name {font-weight: 700;}
.stock-box .c-qty {font-weight: 600; background: rgba(128,128,128,.22);
    padding: .15rem .6rem; border-radius: 8px; font-size: .85rem; white-space: nowrap;}
.home-line {padding: .3rem 0; font-size: .9rem;}
.cat-head {font-weight: 700; font-size: .9rem; margin: .6rem 0 .1rem; padding-left: .1rem;
    border-left: 4px solid #0f766e; padding: .05rem .5rem;}
div[data-testid="stCaptionContainer"] {margin-bottom: -.2rem;}
.total-bar {border-radius: 10px; padding: .55rem .9rem; margin: .4rem 0 .6rem;
    background: rgba(15,118,110,.14); border: 1px solid rgba(15,118,110,.35); font-weight: 700;}

@media (max-width: 640px) {
    [data-testid="stNumberInputStepUp"], [data-testid="stNumberInputStepDown"] {display: none;}
    div[data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important; gap: .4rem !important;}
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"],
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {min-width: 0 !important;}
}
</style>
""", unsafe_allow_html=True)


# ---------- Password (ek baar login, phir link yaad rakhta hai) ----------
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


@st.cache_data(ttl=5)
def load_all():
    rows, start = [], 0
    while True:
        chunk = db().table("orders").select("*").order("id").range(start, start + 999).execute().data
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    for r in rows:
        if not r.get("bill_id"):
            r["bill_id"] = f"bill_{r['id']}"
    df = pd.DataFrame(rows)
    for col in COLS:
        if col not in df.columns:
            df[col] = None
    df = df[COLS].copy()
    df["cartons"] = pd.to_numeric(df["cartons"]).fillna(0.0).astype(float)
    df["priority"] = df["priority"].fillna(False).astype(bool)
    for c in ["bill_id", "category", "vendor", "size", "color", "status", "ordered_on", "received_on"]:
        df[c] = df[c].fillna("").astype(str)
    df["size_num"] = pd.to_numeric(
        df["size"].str.extract(r"(\d+\.?\d*)", expand=False), errors="coerce").fillna(9999)
    return df


@st.cache_data(ttl=5)
def load_godown():
    rows, start = [], 0
    while True:
        try:
            chunk = db().table("godown_stock").select("*").order("id").range(start, start + 999).execute().data
        except Exception:
            break
        rows += chunk
        if len(chunk) < 1000:
            break
        start += 1000
    df = pd.DataFrame(rows)
    for col in GODOWN_COLS:
        if col not in df.columns:
            df[col] = None
    df = df[GODOWN_COLS].copy()
    df["cartons"] = pd.to_numeric(df["cartons"]).fillna(0.0).astype(float)
    for c in ["category", "size", "color"]:
        df[c] = df[c].fillna("").astype(str)
    df["size_num"] = pd.to_numeric(
        df["size"].str.extract(r"(\d+\.?\d*)", expand=False), errors="coerce").fillna(9999)
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


# ---------- Drafts (likha hua database mein khud save hota rehta hai) ----------
def get_draft(name, dkey, base):
    ss = st.session_state
    if name not in ss:
        b = copy.deepcopy(base)
        try:
            rows = db().table("drafts").select("*").eq("key", dkey).execute().data
            if rows and rows[0].get("data"):
                b.update(rows[0]["data"])
        except Exception:
            ss["draft_ok"] = False
        for l in b.get("lines", []):
            if "uid" not in l:
                l["uid"] = new_uid(b["lines"])
        ss[name] = b
        ss[f"{name}__key"] = dkey
    return ss[name]


def save_draft(name):
    try:
        db().table("drafts").upsert({"key": st.session_state[f"{name}__key"],
                                     "data": st.session_state[name]}).execute()
    except Exception:
        st.session_state["draft_ok"] = False


def new_uid(lines):
    return max([int(l.get("uid", 0)) for l in lines] + [0]) + 1


try:
    alld = load_all()
    godown_df = load_godown()
except Exception as e:
    st.error("Database se connect nahi ho saka. Supabase project check karein "
             "(paused ho to 'Resume project' dabayen).")
    st.caption(str(e))
    st.stop()

otw = alld[alld["status"] == "on_the_way"]


# ---------- Helpers ----------
def fmt(x):
    try:
        x = float(x)
    except Exception:
        return str(x)
    return str(int(x)) if x.is_integer() else f"{x:g}"


def esc(x):
    return html.escape(str(x))


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


def options_for(cat, extra_lines=()):
    """Size/color ki list SIRF is category ki (orders + godown + abhi likhi hui lines)."""
    o = alld[alld["category"] == cat]
    g = godown_df[godown_df["category"] == cat]
    ex = [l for l in extra_lines if l.get("category") == cat]
    sizes = {x for x in o["size"] if x} | {x for x in g["size"] if x} | {clean_size(l["size"]) for l in ex}
    colors = {x for x in o["color"] if x} | {x for x in g["color"] if x} | {clean_text(l["color"]) for l in ex}
    return sorted(sizes, key=size_key), sorted(colors, key=str.lower)


def smart_selectbox(label, options, value, key):
    opts = list(options)
    if value and value not in opts:
        opts = [value] + opts
    idx = opts.index(value) if value in opts else None
    kwargs = {"index": idx, "placeholder": f"{label} chunein ya likhein", "key": key}
    if "accept_new_options" in inspect.signature(st.selectbox).parameters:
        kwargs["accept_new_options"] = True
    return st.selectbox(label, opts, **kwargs)


def entry_form(prefix, cat, extra_lines=(), with_priority=False, btn="➕ Jorein"):
    """Size | Color | Carton ek hi line mein. Jorein dabane par dict wapas deta hai aur form khali ho jata
    hai (size wahi rehta hai taake agla color jaldi likha jaye)."""
    ss = st.session_state
    n = ss.setdefault(f"{prefix}_n", 0)
    sizes, colors = options_for(cat, extra_lines)
    last = ss.get(f"{prefix}_last", "")
    c1, c2, c3 = st.columns([2, 2, 1.5])
    with c1:
        sz_raw = smart_selectbox("Size", sizes, last if last in sizes else "", key=f"{prefix}_sz_{n}_{cat}")
    with c2:
        cl_raw = smart_selectbox("Color", colors, "", key=f"{prefix}_cl_{n}_{cat}")
    qty = c3.number_input("Cartons", min_value=0.5, step=0.5, value=None, placeholder="Qty",
                          key=f"{prefix}_q_{n}")
    sz = clean_size(sz_raw) if sz_raw else ""
    cl = clean_text(cl_raw) if cl_raw else ""
    if with_priority:
        b1, b2 = st.columns([1.2, 2.8])
        pri = b1.checkbox("⭐ Priority", key=f"{prefix}_p_{n}")
        clicked = b2.button(btn, type="primary", key=f"{prefix}_add_{n}", disabled=not (sz and cl and qty))
    else:
        pri = False
        clicked = st.button(btn, type="primary", key=f"{prefix}_add_{n}", disabled=not (sz and cl and qty))
    if clicked:
        ss[f"{prefix}_n"] = n + 1
        ss[f"{prefix}_last"] = sz
        return {"category": cat, "size": sz, "color": cl, "cartons": float(qty), "priority": bool(pri)}
    return None


def grouped(lines):
    order = list(dict.fromkeys(l["category"] for l in lines))
    return sorted(lines, key=lambda l: order.index(l["category"]))


def edit_rows(prefix, rows, with_pri=False, mark_delete=False, group="category"):
    """Har jagah ek jaisa edit interface: Size | Color | Ctn (| ⭐) | 🗑️ ek hi line mein.
    rows: dicts jin mein uid, category, size, color, cartons, priority.
    mark_delete=True: 🗑️ sirf nishaan lagata hai (↩️ se wapas), asal delete 'Save' par hota hai.
    mark_delete=False: 🗑️ turant line hata deta hai (sirf draft ki lines ke liye).
    Wapas deta hai: (edited, marks, clicked_uid)."""
    ss = st.session_state
    marks = ss.setdefault(f"{prefix}_marks", set())
    widths = [2.3, 2.3, 1.7, 0.8, 0.9] if with_pri else [2.6, 2.6, 1.8, 0.9]
    heads = ["Size", "Color", "Ctn"] + (["⭐"] if with_pri else []) + [""]
    edited, clicked, last_grp, first = {}, None, object(), True

    def header():
        for c_, t_ in zip(st.columns(widths), heads):
            c_.caption(t_)

    for r in rows:
        uid = r["uid"]
        if group and r.get(group) != last_grp:
            last_grp = r.get(group)
            st.markdown(f'<div class="cat-head">{esc(last_grp)}</div>', unsafe_allow_html=True)
            header()
        elif not group and first:
            header()
        first = False
        marked = uid in marks
        cols = st.columns(widths)
        sz = cols[0].text_input("Size", value=r["size"], key=f"{prefix}_sz_{uid}",
                                label_visibility="collapsed", disabled=marked)
        cl = cols[1].text_input("Color", value=r["color"], key=f"{prefix}_cl_{uid}",
                                label_visibility="collapsed", disabled=marked)
        qt = cols[2].number_input("Ctn", min_value=0.5, step=0.5, format="%g",
                                  value=max(float(r["cartons"]), 0.5), key=f"{prefix}_q_{uid}",
                                  label_visibility="collapsed", disabled=marked)
        pr = bool(r.get("priority"))
        if with_pri:
            pr = cols[3].checkbox("⭐", value=pr, key=f"{prefix}_p_{uid}",
                                  label_visibility="collapsed", disabled=marked)
        if cols[-1].button("↩️" if marked else "🗑️", key=f"{prefix}_x_{uid}",
                           help="Wapas rakhein" if marked else "Hatayen"):
            if mark_delete:
                marks.discard(uid) if marked else marks.add(uid)
                st.rerun()
            else:
                clicked = uid
        edited[uid] = {"size": clean_size(sz) or r["size"], "color": clean_text(cl) or r["color"],
                       "cartons": float(qt), "priority": pr}
    return edited, marks, clicked


def changed(old, new, with_pri):
    keys = ["size", "color", "cartons"] + (["priority"] if with_pri else [])
    return any(old.get(k) != new.get(k) for k in keys)


def draft_rows_ui(name, prefix, with_pri):
    """Draft ki lines: inline edit (khud save), 🗑️ se turant hatana, neeche total."""
    lines = st.session_state[name]["lines"]
    edited, _, clicked = edit_rows(prefix, grouped(lines), with_pri=with_pri)
    if clicked is not None:
        lines[:] = [l for l in lines if l["uid"] != clicked]
        save_draft(name)
        st.rerun()
    dirty = False
    for l in lines:
        e = edited.get(l["uid"])
        if e and changed(l, {**e, "priority": e["priority"] if with_pri else l.get("priority", False)}, with_pri):
            l.update(e if with_pri else {k: v for k, v in e.items() if k != "priority"})
            dirty = True
    if dirty:
        save_draft(name)
    st.markdown(f'<div class="total-bar">Total: {fmt(sum(float(l["cartons"]) for l in lines))} carton'
                f' • {len(lines)} lines</div>', unsafe_allow_html=True)


def draft_notice():
    if st.session_state.get("draft_ok") is False:
        st.warning("Auto-save abhi band hai (migration2.sql Run nahi hui). "
                   "Doosri app kholne se ye list ud sakti hai.")
    else:
        st.caption("💾 Jo likhte hain wo khud save hota rehta hai. Doosri app khol kar wapas aayen "
                   "to list wahi milegi.")


# ---------- Home List ----------
def render_list(d, manage, kp):
    if d.empty:
        st.info("Koi maal nahi mila.")
        return
    d = sort_df(d)
    for (size, color), g in d.groupby(["size", "color"], sort=False):
        star = " ⭐" if g["priority"].any() else ""
        with st.expander(f"{size} {color}{star} — {fmt(g['cartons'].sum())} carton"):
            if manage:
                has_pri = bool(g["priority"].any())
                if st.button("⭐ Priority hatayen" if has_pri else "⭐ Priority lagayen",
                             key=f"{kp}pg{size}_{color}"):
                    update_rows(g["id"].tolist(), {"priority": not has_pri})
                    st.rerun()
                st.divider()
            for _, r in g.iterrows():
                v_name = r["vendor"] or NO_VENDOR
                qty = fmt(r["cartons"])
                c_info, c_rcv, c_ed, c_del = st.columns([5.2, 1.3, 1.3, 1.1])
                c_info.markdown(
                    f'<div class="home-line">• <b>{esc(v_name)}</b> | {esc(r["color"])} | '
                    f'<b>{qty} ctn</b> | 📅 {esc(r["ordered_on"])}</div>', unsafe_allow_html=True)
                if c_rcv.button("✅", help="Received mark karein", key=f"{kp}rcv{r['id']}"):
                    update_rows([r["id"]], {"status": "received", "received_on": str(date.today())})
                    st.session_state["last_rcv"] = {
                        "ids": [int(r["id"])], "label": f"{size} {color} ({v_name}: {qty} carton)"}
                    st.rerun()
                with c_ed.popover("✏️"):
                    nv = st.text_input("Vendor", value=r["vendor"], key=f"{kp}v{r['id']}")
                    nsz = st.text_input("Size", value=r["size"], key=f"{kp}sz{r['id']}")
                    ncol = st.text_input("Color", value=r["color"], key=f"{kp}cl{r['id']}")
                    nc = st.number_input("Cartons", min_value=0.5, step=0.5,
                                         value=max(float(r["cartons"]), 0.5), key=f"{kp}c{r['id']}")
                    npri = st.checkbox("⭐ Priority", value=bool(r["priority"]), key=f"{kp}s{r['id']}")
                    if st.button("Save", key=f"{kp}sv{r['id']}"):
                        update_rows([r["id"]], {"vendor": clean_text(nv), "size": clean_size(nsz),
                                                "color": clean_text(ncol), "cartons": float(nc),
                                                "priority": bool(npri)})
                        st.session_state["msg"] = "Updated ✅"
                        st.rerun()
                if c_del.button("🗑️", help="Permanent Delete", key=f"{kp}del{r['id']}"):
                    delete_row(r["id"])
                    st.session_state["msg"] = f"{v_name} ({size} {r['color']}) delete ho gaya 🗑️"
                    st.rerun()


# ======================= HEADER =======================
unrec = otw.sort_values(by=["size_num", "size"])[["ordered_on", "size", "color", "cartons", "category"]].copy()
unrec.columns = ["Date", "Size", "Color", "Carton Quantity", "Category"]

h1, h2 = st.columns([5, 1.3])
h1.title("📦 Stock On The Way")
with h2.popover("⚙️"):
    st.download_button("📥 Unreceived CSV", unrec.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"unreceived_stock_{date.today()}.csv", mime="text/csv", key="dl_unrec")
    st.download_button("💾 Poora backup CSV",
                       alld.drop(columns=["size_num"]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"stock_backup_{date.today()}.csv", mime="text/csv", key="dl_full")

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

# ---------- Navigation (tab yaad rehta hai, app dobara khulne par bhi) ----------
if "tab" not in st.session_state:
    try:
        st.session_state["tab"] = NAV[int(st.query_params.get("tab", 0))]
    except Exception:
        st.session_state["tab"] = NAV[0]
tab = st.radio("Navigation", NAV, horizontal=True, label_visibility="collapsed", key="tab")
if st.query_params.get("tab") != str(NAV.index(tab)):
    st.query_params["tab"] = str(NAV.index(tab))
st.markdown("---")
ss = st.session_state

# ======================= 1. STOCK SEARCH =======================
if tab == NAV[0]:
    st.subheader("Stock Search (Godown + On The Way)")
    s_cat = st.radio("Category", CATEGORIES, horizontal=True, key="search_cat")
    cat_otw = otw[otw["category"] == s_cat]
    cat_gdn = godown_df[godown_df["category"] == s_cat]
    sizes = sorted(set(cat_otw["size"]) | set(cat_gdn["size"]), key=size_key)

    if not sizes:
        st.info(f"'{s_cat}' category mein koi stock nahi hai.")
    else:
        s_size = st.selectbox("Size", sizes, key=f"search_size_{s_cat}")
        g_sum = cat_gdn[cat_gdn["size"] == s_size].groupby("color")["cartons"].sum().to_dict()
        o_sum = cat_otw[cat_otw["size"] == s_size].groupby("color")["cartons"].sum().to_dict()
        colors = sorted(set(g_sum) | set(o_sum), key=str.lower)
        st.markdown(f"### 📊 Size: **{esc(s_size)}** ({esc(s_cat)})")
        st.caption("🏢 = Godown   🚢 = On the way")
        for col in colors:
            g, o = g_sum.get(col, 0.0), o_sum.get(col, 0.0)
            st.markdown(
                f'<div class="stock-box"><span class="c-name">{esc(col)}</span>'
                f'<span class="c-qty">🏢 {fmt(g)} | 🚢 {fmt(o)} | Tot: <b>{fmt(g + o)} ctn</b></span></div>',
                unsafe_allow_html=True)

# ======================= 2. GODOWN =======================
elif tab == NAV[1]:
    st.subheader("🏢 Godown Stock")
    g_cat = st.radio("Category", CATEGORIES, horizontal=True, key="g_cat_sel")
    mode = st.radio("Kaam", ["➕ Bulk Add", "✏️ Update / Delete"], horizontal=True,
                    label_visibility="collapsed", key="g_mode")

    if mode == "➕ Bulk Add":
        gd = get_draft("gdraft", "godown", {"lines": []})
        draft_notice()
        st.markdown(f"##### ➕ Maal jorein — {esc(g_cat)}")
        item = entry_form("gd", g_cat, gd["lines"], False, "➕ List mein jorein")
        if item:
            item["uid"] = new_uid(gd["lines"])
            gd["lines"].append(item)
            save_draft("gdraft")
            st.rerun()

        if gd["lines"]:
            st.markdown("##### 🧾 Save hone wala maal — kuch galat ho to yahin badlein ya 🗑️")
            draft_rows_ui("gdraft", "gdl", with_pri=False)
            if st.button("💾 Sab Godown mein Save Karein", type="primary", key="g_save_all"):
                agg = {}
                for l in gd["lines"]:
                    k = (l["category"], l["size"], l["color"])
                    agg[k] = agg.get(k, 0.0) + float(l["cartons"])
                try:
                    for (c_, s_, cl_), q_ in agg.items():
                        ex = db().table("godown_stock").select("*").eq("category", c_) \
                            .eq("size", s_).eq("color", cl_).execute().data
                        if ex:
                            db().table("godown_stock").update(
                                {"cartons": float(ex[0]["cartons"]) + q_}).eq("id", ex[0]["id"]).execute()
                        else:
                            db().table("godown_stock").insert(
                                {"category": c_, "size": s_, "color": cl_, "cartons": q_}).execute()
                except Exception as e:
                    st.error("Save nahi ho saka. List mehfooz hai, dobara koshish karein.")
                    st.caption(str(e))
                    st.stop()
                clear_cache()
                gd["lines"] = []
                save_draft("gdraft")
                ss["msg"] = f"Godown mein {len(agg)} items save ho gaye 🎉"
                st.rerun()
            with st.expander("🧹 Poori list saaf karein"):
                if st.button("Haan, saari lines mita dein", key="g_clear"):
                    gd["lines"] = []
                    save_draft("gdraft")
                    st.rerun()

    else:
        fg = godown_df[godown_df["category"] == g_cat]
        if fg.empty:
            st.info(f"'{g_cat}' mein godown ka koi stock nahi hai.")
        else:
            st.caption("Jitni lines chahein badlein, 🗑️ se delete ka nishaan lagayen, phir neeche ek sath Save karein.")
            fg = fg.sort_values(["size_num", "size", "color", "id"])
            rows = [{"uid": int(r.id), "category": r.category, "size": r.size, "color": r.color,
                     "cartons": float(r.cartons)} for r in fg.itertuples()]
            orig = {r["uid"]: r for r in rows}
            edited, marks, _ = edit_rows(f"gu_{g_cat}", rows, with_pri=False, mark_delete=True, group=None)
            ups = [u for u, e in edited.items() if u not in marks and changed(orig[u], e, False)]
            dels = [u for u in marks if u in orig]
            n_ch = len(ups) + len(dels)
            st.markdown(f'<div class="total-bar">Total: {fmt(fg["cartons"].sum())} carton</div>',
                        unsafe_allow_html=True)
            if st.button(f"💾 Save Changes ({len(ups)} badlav • {len(dels)} delete)", type="primary",
                         disabled=n_ch == 0, key="gu_save"):
                for u in ups:
                    e = edited[u]
                    db().table("godown_stock").update(
                        {"size": e["size"], "color": e["color"], "cartons": e["cartons"]}).eq("id", u).execute()
                if dels:
                    db().table("godown_stock").delete().in_("id", dels).execute()
                clear_cache()
                ss[f"gu_{g_cat}_marks"] = set()
                ss["msg"] = f"Godown update ho gaya ✅ ({len(ups)} badlav, {len(dels)} delete)"
                st.rerun()

# ======================= 3. HOME =======================
elif tab == NAV[2]:
    tc1, tc2 = st.columns(2)
    manage = tc1.toggle("🛠 Priority Controls", key="manage")
    only_pri = tc2.toggle("⭐ Sirf Priority", value=True, key="only_pri")
    q = st.text_input("Search", placeholder="🔍 Size, color ya vendor search karein...",
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
            st.success(f"{cat} Total: {fmt(dc['cartons'].sum())} cartons")
    else:
        for cat, ctab in zip(cats, st.tabs(cats)):
            with ctab:
                dc = d[d["category"] == cat]
                if dc.empty:
                    st.info("Priority wala koi maal nahi." if only_pri
                            else "Is category mein koi maal on the way nahi.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                st.success(f"{cat} Total: {fmt(dc['cartons'].sum())} cartons")

# ======================= 4. VENDOR BILL =======================
elif tab == NAV[3]:
    st.subheader("🧾 Vendor-Wise Bills")
    if "vb_pending" in ss:                      # vendor ka naam badalne ke baad wahi vendor khula rahe
        ss["vb_vendor"] = ss.pop("vb_pending")
    vendors = sorted({v for v in otw["vendor"] if v}, key=str.lower)
    if not vendors:
        st.info("Abhi koi vendor bill on the way nahi hai.")
        sel_v = None
    else:
        sel_v = st.selectbox("Vendor", vendors, index=None, placeholder="Vendor chunein", key="vb_vendor")

    if sel_v:
        v_otw = otw[otw["vendor"] == sel_v].sort_values(["ordered_on", "id"])
        bill_ids = list(dict.fromkeys(v_otw["bill_id"]))
        labels = {}
        for n_, b_ in enumerate(bill_ids, 1):
            bd = v_otw[v_otw["bill_id"] == b_]
            labels[b_] = f"Bill {n_} • {bd['ordered_on'].iloc[0]} • {fmt(bd['cartons'].sum())} ctn • {len(bd)} items"
        sel_b = st.selectbox("Bill", bill_ids, format_func=lambda b: labels[b], key=f"vb_bill_{sel_v}")
        b_data = sort_df(v_otw[v_otw["bill_id"] == sel_b])
        b_date = b_data["ordered_on"].iloc[0]
        editing = st.toggle("✏️ Edit mode (item add / edit / delete)", key=f"vb_edit_{sel_b}")

        if not editing:
            show = b_data[["category", "size", "color", "cartons"]].copy()
            show["cartons"] = show["cartons"].map(fmt)
            show.columns = ["Category", "Size", "Color", "Carton"]
            st.dataframe(show, hide_index=True)
            st.markdown(f'<div class="total-bar">Total: {fmt(b_data["cartons"].sum())} carton • '
                        f'{len(b_data)} items</div>', unsafe_allow_html=True)
            if st.button("✅ Poora Bill Received Mark Karein", type="primary", key=f"vb_rcv_{sel_b}"):
                db().table("orders").update({"status": "received", "received_on": str(date.today())}) \
                    .eq("bill_id", sel_b).execute()
                clear_cache()
                ss["last_rcv"] = {"ids": [int(x) for x in b_data["id"]],
                                  "label": f"{sel_v} ka bill ({fmt(b_data['cartons'].sum())} carton)"}
                st.rerun()
        else:
            st.markdown("##### Bill ki maloomat")
            m1, m2 = st.columns([3, 2])
            new_vendor = m1.text_input("Vendor", value=sel_v, key=f"vb_nv_{sel_b}")
            try:
                parsed = date.fromisoformat(b_date)
            except Exception:
                parsed = date.today()
            new_date = m2.date_input("Date", value=parsed, key=f"vb_nd_{sel_b}")
            if st.button("💾 Vendor / Date Save Karein", key=f"vb_meta_{sel_b}"):
                db().table("orders").update({"vendor": clean_text(new_vendor), "ordered_on": str(new_date)}) \
                    .eq("bill_id", sel_b).execute()
                clear_cache()
                ss["vb_pending"] = clean_text(new_vendor)
                ss["msg"] = "Bill ki maloomat save ho gayin ✅"
                st.rerun()

            st.markdown("##### Maujooda items — jitne chahein badlein, 🗑️ se delete ka nishaan lagayen")
            rows = [{"uid": int(r.id), "category": r.category, "size": r.size, "color": r.color,
                     "cartons": float(r.cartons), "priority": bool(r.priority)} for r in b_data.itertuples()]
            orig = {r["uid"]: r for r in rows}
            edited, marks, _ = edit_rows(f"vbe_{sel_b}", rows, with_pri=True, mark_delete=True)

            st.markdown("##### ➕ Naye items jorein")
            pend_name = f"vbadd_{sel_b}"
            pend = get_draft(pend_name, pend_name, {"lines": []})
            add_cat = st.radio("Category", CATEGORIES,
                               index=CATEGORIES.index(b_data["category"].iloc[-1])
                               if b_data["category"].iloc[-1] in CATEGORIES else 0,
                               horizontal=True, key=f"vb_cat_{sel_b}")
            item = entry_form(f"vba_{sel_b}", add_cat, pend["lines"], True, "➕ List mein jorein")
            if item:
                item["uid"] = new_uid(pend["lines"])
                pend["lines"].append(item)
                save_draft(pend_name)
                st.rerun()
            if pend["lines"]:
                st.markdown("##### 🧾 Naye items (abhi save nahi hue)")
                draft_rows_ui(pend_name, f"vbp_{sel_b}", with_pri=True)

            ups = [u for u, e in edited.items() if u not in marks and changed(orig[u], e, True)]
            dels = [u for u in marks if u in orig]
            n_new = len(pend["lines"])
            st.markdown(f'<div class="total-bar">Bill ka total (maujooda): {fmt(b_data["cartons"].sum())} carton'
                        f'</div>', unsafe_allow_html=True)
            if st.button(f"💾 Sab Save Karein ({len(ups)} badlav • {len(dels)} delete • {n_new} naye)",
                         type="primary", disabled=(len(ups) + len(dels) + n_new) == 0, key=f"vb_all_{sel_b}"):
                try:
                    for u in ups:
                        db().table("orders").update(edited[u]).eq("id", u).execute()
                    if dels:
                        db().table("orders").delete().in_("id", dels).execute()
                    if n_new:
                        db().table("orders").insert([{
                            "bill_id": sel_b, "vendor": sel_v, "category": l["category"], "size": l["size"],
                            "color": l["color"], "cartons": float(l["cartons"]),
                            "priority": bool(l.get("priority")), "ordered_on": b_date or str(date.today()),
                            "status": "on_the_way"} for l in pend["lines"]]).execute()
                except Exception as e:
                    st.error("Save poora nahi ho saka. Dobara koshish karein.")
                    st.caption(str(e))
                    st.stop()
                clear_cache()
                pend["lines"] = []
                save_draft(pend_name)
                ss[f"vbe_{sel_b}_marks"] = set()
                ss["msg"] = f"Bill update ho gaya ✅ ({len(ups)} badlav, {len(dels)} delete, {n_new} naye)"
                st.rerun()

# ======================= 5. NAYA BILL =======================
elif tab == NAV[4]:
    dr = get_draft("draft", "main", {"vendor": "", "category": CATEGORIES[0],
                                     "order_date": str(date.today()), "lines": []})
    st.subheader("➕ Naya Vendor Bill")
    draft_notice()
    vk = ss.setdefault("nb_vk", 0)

    c1, c2 = st.columns([3, 2])
    vend_opts = sorted({v for v in alld["vendor"] if v}, key=str.lower)
    with c1:
        picked = smart_selectbox("Vendor", vend_opts, dr.get("vendor", ""), key=f"nb_v_{vk}")
    vendor = clean_text(picked) if picked else ""
    if vendor != dr.get("vendor", ""):
        dr["vendor"] = vendor
        save_draft("draft")
    try:
        parsed = date.fromisoformat(dr.get("order_date", ""))
    except Exception:
        parsed = date.today()
    with c2:
        sel_date = st.date_input("Date", value=parsed, key=f"nb_d_{vk}")
    if str(sel_date) != dr.get("order_date"):
        dr["order_date"] = str(sel_date)
        save_draft("draft")

    cat = st.radio("Category", CATEGORIES,
                   index=CATEGORIES.index(dr["category"]) if dr.get("category") in CATEGORIES else 0,
                   horizontal=True, key="nb_cat")
    if cat != dr.get("category"):
        dr["category"] = cat
        save_draft("draft")

    st.markdown(f"##### ➕ Item jorein — {esc(cat)}")
    item = entry_form("nb", cat, dr["lines"], True, "➕ Bill mein jorein")
    if item:
        item["uid"] = new_uid(dr["lines"])
        dr["lines"].append(item)
        save_draft("draft")
        st.rerun()

    if dr["lines"]:
        st.markdown(f"##### 🧾 Current Bill — **{esc(vendor) if vendor else '⚠️ Vendor chunein'}**")
        st.caption("Kuch galat ho to seedha yahin badlein ya 🗑️ dabayen.")
        draft_rows_ui("draft", "nbl", with_pri=True)
        if st.button("💾 Poora Bill Save Karein", type="primary", disabled=not vendor, key="nb_save"):
            bid = f"bill_{int(time.time() * 1000)}"
            rows = [{"bill_id": bid, "vendor": vendor, "category": l["category"], "size": l["size"],
                     "color": l["color"], "cartons": float(l["cartons"]), "priority": bool(l.get("priority")),
                     "ordered_on": dr["order_date"], "status": "on_the_way"} for l in dr["lines"]]
            try:
                db().table("orders").insert(rows).execute()
            except Exception as e:
                st.error("Bill save nahi ho saka. List mehfooz hai, dobara koshish karein.")
                st.caption(str(e))
                st.stop()
            clear_cache()
            dr["lines"], dr["vendor"] = [], ""
            save_draft("draft")
            ss["nb_vk"] += 1
            ss["msg"] = f"{vendor} ka bill save ho gaya 🎉"
            st.rerun()
        if not vendor:
            st.caption("Save karne se pehle upar Vendor chunein.")
        with st.expander("🧹 Poora bill saaf karein"):
            if st.button("Haan, saari lines mita dein", key="nb_clear"):
                dr["lines"] = []
                save_draft("draft")
                st.rerun()

# ======================= 6. HISTORY =======================
elif tab == NAV[5]:
    st.subheader("📜 Receive ho chuka maal")
    hk = ss.setdefault("hk", 0)
    rec = alld[alld["status"] == "received"]
    f1, f2 = st.columns(2)
    fc = f1.selectbox("Category", ["Sab"] + CATEGORIES, key="h_cat")
    hq = f2.text_input("Search", placeholder="🔍 Search", key="h_q", label_visibility="collapsed")
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
            disabled=[c for c in view.columns if c != "Select"])
        ids = [int(x) for x in edited.loc[edited["Select"], "id"]]
        st.caption(f"{len(ids)} select hue • Total dikh rahe: {fmt(rec['cartons'].sum())} carton")
        if st.button("↩️ Wapas On the Way", disabled=not ids, type="primary", key="h_back"):
            db().table("orders").update({"status": "on_the_way", "received_on": None}) \
                .in_("id", ids).eq("status", "received").execute()
            clear_cache()
            ss["hk"] += 1
            ss["msg"] = f"{len(ids)} entry wapas on the way ✅"
            st.rerun()
        sure = st.checkbox("Haan, select kiye hue ko pakka delete karna hai", key=f"h_sure{hk}")
        if st.button("🗑️ Select kiye delete karein", disabled=not (ids and sure), key="h_del"):
            # sirf 'received' wali rows delete hongi, on_the_way ko kabhi haath nahi lagta
            db().table("orders").delete().in_("id", ids).eq("status", "received").execute()
            clear_cache()
            ss["hk"] += 1
            ss["msg"] = f"{len(ids)} entry delete ho gayi 🗑️"
            st.rerun()
