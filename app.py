import re
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

# ======================= SETTINGS (yahan khud badal sakte hain) =======================
CATEGORIES = ["Crystal", "Pod", "Shelper"]   # nayi category yahan add karein
CURRENCY = "RMB"                              # price ki currency
COLS = ["id", "category", "size", "color", "cartons", "price_per_carton",
        "priority", "status", "ordered_on", "received_on"]
NEW = "➕ Naya likhein"
# ======================================================================================

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
    rows = db().table("orders").select("*").order("id", desc=True).execute().data
    df = pd.DataFrame(rows, columns=COLS)
    df["cartons"] = df["cartons"].astype(int)
    df["price_per_carton"] = df["price_per_carton"].astype(float)
    df["priority"] = df["priority"].astype(bool)
    df["size_num"] = df["size"].str.extract(r"(\d+\.?\d*)", expand=False).astype(float)
    return df


try:
    alld = load_all()
except Exception as e:
    st.error("Database se connect nahi ho saka. Agar Supabase project 'paused' hai "
             "to Supabase dashboard mein jaa kar 'Resume project' dabayen. Data mehfooz hai.")
    st.caption(str(e))
    st.stop()

otw = alld[alld["status"] == "on_the_way"]

st.title("📦 China se On The Way")
if "msg" in st.session_state:
    st.success(st.session_state.pop("msg"))

tabs = st.tabs(CATEGORIES + ["➕ Naya order", "📜 History / Backup"])

# ---------- Category tabs ----------
for cat, tab in zip(CATEGORIES, tabs[: len(CATEGORIES)]):
    with tab:
        only_pri = st.toggle("⭐ Sirf priority wala maal", key=f"pri_{cat}")
        d = otw[otw["category"] == cat]
        if only_pri:
            d = d[d["priority"]]
        if d.empty:
            st.info("Is category mein koi maal on the way nahi.")
            continue

        grand = (d["cartons"] * d["price_per_carton"]).sum()
        st.caption(f"Total: {d['cartons'].sum()} carton • {grand:,.0f} {CURRENCY}")

        for size, g in d.sort_values("size_num").groupby("size", sort=False):
            tc = g["cartons"].sum()
            tp = (g["cartons"] * g["price_per_carton"]).sum()
            with st.expander(f"{size} — {tc} carton — {tp:,.0f} {CURRENCY}"):
                for _, r in g.iterrows():
                    star = " ⭐" if r["priority"] else ""
                    st.markdown(f"**{r['color']}**{star}")
                    st.write(
                        f"{r['cartons']} carton × {r['price_per_carton']:,.2f} = "
                        f"**{r['cartons'] * r['price_per_carton']:,.2f} {CURRENCY}**  \n"
                        f"📅 Order: {r['ordered_on']}"
                    )
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Received", key=f"rcv{r['id']}"):
                        db().table("orders").update(
                            {"status": "received", "received_on": str(date.today())}
                        ).eq("id", int(r["id"])).execute()
                        st.session_state["msg"] = f"{size} {r['color']} receive ho gaya ✅"
                        st.rerun()
                    with c2.popover("✏️ Badlein"):
                        nc = st.number_input("Cartons", min_value=1, step=1,
                                             value=int(r["cartons"]), key=f"c{r['id']}")
                        npz = st.number_input("Price per carton", min_value=0.0,
                                              value=float(r["price_per_carton"]),
                                              key=f"p{r['id']}")
                        npri = st.checkbox("⭐ Priority", value=bool(r["priority"]),
                                           key=f"s{r['id']}")
                        if st.button("Save", key=f"sv{r['id']}"):
                            db().table("orders").update(
                                {"cartons": int(nc), "price_per_carton": float(npz),
                                 "priority": bool(npri)}
                            ).eq("id", int(r["id"])).execute()
                            st.session_state["msg"] = "Badlav save ho gaya ✅"
                            st.rerun()
                    st.divider()


# ---------- Naya order ----------
def pick(label, options, key):
    choice = st.selectbox(label, options + [NEW], key=key)
    if choice == NEW:
        return st.text_input(f"Naya {label}", key=key + "_new").strip()
    return choice


with tabs[len(CATEGORIES)]:
    st.subheader("Naya order likhein")
    cat = st.selectbox("Category", CATEGORIES, key="n_cat")
    in_cat = alld[alld["category"] == cat]
    size_opts = list(in_cat.drop_duplicates("size").sort_values("size_num")["size"])
    size = pick("Size", size_opts, "n_size").lower()
    color_opts = sorted(in_cat["color"].unique())
    color = pick("Color", color_opts, "n_color").title()

    sure = True
    if size and color:
        dup = otw[(otw["category"] == cat) & (otw["size"] == size) & (otw["color"] == color)]
        if not dup.empty:
            st.warning(f"⚠️ {size} {color} ke {dup['cartons'].sum()} carton pehle se "
                       f"on the way hain!")
            sure = st.checkbox("Phir bhi naya order add karna hai", key="n_sure")

    cartons = st.number_input("Cartons", min_value=1, step=1, key="n_cartons")
    price = st.number_input(f"Price per carton ({CURRENCY})", min_value=0.0, key="n_price")
    st.write(f"**Total: {cartons * price:,.2f} {CURRENCY}**")
    pri = st.checkbox("⭐ Priority (zyada bikne wala)", key="n_pri")

    if st.button("💾 Save order", type="primary", disabled=not (size and color and sure)):
        db().table("orders").insert({
            "category": cat, "size": size, "color": color,
            "cartons": int(cartons), "price_per_carton": float(price),
            "priority": bool(pri),
        }).execute()
        st.session_state["msg"] = f"{size} {color} — {cartons} carton save ho gaye ✅"
        st.rerun()


# ---------- History / Backup ----------
with tabs[-1]:
    st.subheader("Receive ho chuka maal")
    rec = alld[alld["status"] == "received"].drop(columns=["size_num", "status"])
    st.dataframe(rec)
    st.subheader("Backup")
    st.caption("Har hafte ek baar ye CSV download karke rakh lein.")
    st.download_button(
        "⬇️ Poora data CSV backup",
        alld.drop(columns=["size_num"]).to_csv(index=False).encode("utf-8-sig"),
        file_name=f"stock_backup_{date.today()}.csv",
        mime="text/csv",
    )
