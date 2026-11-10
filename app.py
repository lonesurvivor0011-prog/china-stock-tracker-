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


# ---------- Password ----------
def check_password():
    if st.session_state.get("ok"):
        return True
    pw = st.text_input("Password", type="password")
    if pw and pw == st.secrets["APP_PASSWORD"]:
        st.session_state["ok"] = True
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
    while True:   # 1000 se zyada rows hon tab bhi sab aayen
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


try:
    alld = load_all()
except Exception as e:
    st.error("Database se connect nahi ho saka. Agar Supabase project 'paused' hai "
             "to Supabase dashboard mein jaa kar 'Resume project' dabayen. "
             "Agar migration.sql Run nahi ki to wo pehle Run karein.")
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


def pick(label, options, key, clean):
    """Dropdown (A-Z / chhota se bara) + 'Naya likhein' option."""
    choice = st.selectbox(label, [NEW] + list(options), index=None,
                          placeholder="Chunein ya type karke dhoondein", key=key)
    if choice is None:
        return ""
    if choice == NEW:
        return clean(st.text_input(f"Naya {label} likhein", key=key + "_new"))
    return choice


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
                for _, r in g.iterrows():
                    c1, c2, c3 = st.columns([4, 3, 2])
                    c1.write(f"{r['vendor'] or NO_VENDOR}: {r['cartons']} • {r['ordered_on']}")
                    if c2.button("✅ Received", key=f"{kp}rcv{r['id']}"):
                        update_rows([r["id"]], {"status": "received",
                                                "received_on": str(date.today())})
                        st.session_state["msg"] = f"{size} {color} ({r['vendor']}) receive ho gaya ✅"
                        st.rerun()
                    with c3.popover("✏️"):
                        nv = st.text_input("Vendor", value=r["vendor"], key=f"{kp}v{r['id']}")
                        nc = st.number_input("Cartons", min_value=1, step=1,
                                             value=max(int(r["cartons"]), 1), key=f"{kp}c{r['id']}")
                        npri = st.checkbox("⭐ Priority", value=bool(r["priority"]),
                                           key=f"{kp}s{r['id']}")
                        if st.button("Save", key=f"{kp}sv{r['id']}"):
                            update_rows([r["id"]], {"vendor": clean_text(nv), "cartons": int(nc),
                                                    "priority": bool(npri)})
                            st.session_state["msg"] = "Badlav save ho gaya ✅"
                            st.rerun()


# ======================= PAGE =======================
st.title("📦 China se On The Way")
if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))

tabs = st.tabs(["🏠 Home", "➕ Naya bill", "📜 History / Backup"])

# ---------- HOME ----------
with tabs[0]:
    q = st.text_input("🔍 Search", placeholder="size, color ya vendor likhein (jaise: hopo)")
    t1, t2 = st.columns(2)
    manage = t1.toggle("🛠 Receive / Badlein", key="manage")
    only_pri = t2.toggle("⭐ Sirf priority", key="only_pri")
    d = otw[otw["priority"]] if only_pri else otw
    cats = CATEGORIES + sorted(set(d["category"]) - set(CATEGORIES))

    if q.strip():
        res = search(d, q)
        if res.empty:
            st.info("Is naam ka koi maal on the way nahi.")
        for cat in cats:
            dc = res[res["category"] == cat]
            if dc.empty:
                continue
            st.subheader(cat)
            render_list(dc, manage, f"s{cat}_")
            st.success(f"{cat} ka total: {int(dc['cartons'].sum())} carton")
    else:
        for cat, ctab in zip(cats, st.tabs(cats)):
            with ctab:
                dc = d[d["category"] == cat]
                if dc.empty:
                    st.info("Is category mein koi maal on the way nahi.")
                    continue
                render_list(dc, manage, f"h{cat}_")
                st.success(f"{cat} ka total: {int(dc['cartons'].sum())} carton")

# ---------- NAYA BILL ----------
def txt(x):
    return "" if pd.isna(x) else str(x)


with tabs[1]:
    st.subheader("Naya bill likhein")
    st.session_state.setdefault("gk", 0)
    st.session_state.setdefault("vk", 0)
    gk, vk = st.session_state["gk"], st.session_state["vk"]

    vend_opts = sorted({v for v in alld["vendor"] if v}, key=str.lower)
    vendor = pick("Vendor", vend_opts, f"b_vendor{vk}", clean_text)
    cat = st.selectbox("Category", CATEGORIES, key="b_cat")

    in_cat = alld[alld["category"] == cat]
    ks = sorted({x for x in in_cat["size"] if x}, key=size_key)
    kc = sorted({x for x in in_cat["color"] if x}, key=str.lower)
    if ks or kc:
        st.caption("Pehle se maujood — Size: " + (", ".join(ks) or "-")
                   + "  |  Color: " + (", ".join(kc) or "-"))

    st.markdown("**Size • Color • Carton** — neeche seedha likhte jayein "
                "(size mein sirf `4` likhein to `4mm` ban jayega)")
    blank = pd.DataFrame({"Size": [""] * 8, "Color": [""] * 8,
                          "Cartons": pd.to_numeric(pd.Series([None] * 8))})
    ed = st.data_editor(
        blank, num_rows="dynamic", hide_index=True, key=f"grid{gk}",
        column_config={
            "Size": st.column_config.TextColumn("Size"),
            "Color": st.column_config.TextColumn("Color"),
            "Cartons": st.column_config.NumberColumn("Carton", min_value=1, step=1, format="%d"),
        },
    )

    lines, bad = {}, 0
    for _, r in ed.iterrows():
        s_, c_, n_ = clean_size(txt(r["Size"])), clean_text(txt(r["Color"])), r["Cartons"]
        if not s_ and not c_ and pd.isna(n_):
            continue
        if s_ and c_ and not pd.isna(n_) and int(n_) > 0:
            lines[(s_, c_)] = lines.get((s_, c_), 0) + int(n_)
        else:
            bad += 1
    if bad:
        st.warning(f"{bad} row adhoori hai (size, color ya carton khali). Wo save nahi hogi.")

    if lines:
        order = sorted(lines, key=lambda k: (size_key(k[0]), k[1].lower()))
        st.markdown(f"**Save hone wala bill — {vendor or '❗ vendor chunein'} • {cat}**")
        st.dataframe(pd.DataFrame([{"Size": k[0], "Color": k[1], "Carton": lines[k]} for k in order]),
                     hide_index=True)
        st.write(f"**Bill ka total: {sum(lines.values())} carton ({len(lines)} lines)**")

    if st.button("💾 Poora bill save karein", type="primary", disabled=not (vendor and lines)):
        rows = [{"vendor": vendor, "category": cat, "size": k[0], "color": k[1],
                 "cartons": lines[k], "priority": False} for k in order]
        db().table("orders").insert(rows).execute()
        st.session_state["msg"] = f"{vendor} ka bill save ho gaya ({len(rows)} lines) ✅"
        st.session_state["gk"] += 1
        st.session_state["vk"] += 1
        st.rerun()
    if lines and not vendor:
        st.caption("Save karne se pehle upar Vendor chunein.")

# ---------- HISTORY / BACKUP ----------
with tabs[2]:
    st.subheader("Receive ho chuka maal")
    st.session_state.setdefault("hk", 0)
    hk = st.session_state["hk"]
    rec = alld[alld["status"] == "received"]
    f1, f2 = st.columns(2)
    fc = f1.selectbox("Category", ["Sab"] + CATEGORIES, key="h_cat")
    hq = f2.text_input("🔍 Search", key="h_q")
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
        st.caption(f"{len(ids)} select hue • Total dikh rahe: {int(rec['cartons'].sum())} carton")
        sure = st.checkbox("Haan, select kiye hue ko pakka delete karna hai", key=f"h_sure{hk}")
        b1, b2 = st.columns(2)
        if b1.button("🗑️ Select kiye delete karein", disabled=not (ids and sure)):
            # sirf 'received' wali rows delete hongi, on_the_way ko kabhi haath nahi lagta
            db().table("orders").delete().in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = f"{len(ids)} entry delete ho gayi 🗑️"
            st.rerun()
        if b2.button("↩️ Wapas On the way karein", disabled=not ids):
            db().table("orders").update({"status": "on_the_way", "received_on": None}) \
                .in_("id", ids).eq("status", "received").execute()
            st.session_state["hk"] += 1
            st.session_state["msg"] = f"{len(ids)} entry wapas on the way ✅"
            st.rerun()

    st.subheader("Backup")
    st.caption("Har hafte ek baar ye CSV download karke rakh lein.")
    st.download_button(
        "⬇️ Poora data CSV backup",
        alld.drop(columns=["size_num"]).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"stock_backup_{date.today()}.csv",
        mime="text/csv",
    )
