import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄")

# (ส่วน Login และ Config เดิมของพี่)
if "ok" not in st.session_state:
    st.session_state.ok = False
if not st.session_state.ok:
    pw = st.text_input("รหัสผ่าน", type="password")
    if pw:
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.ok = True
            st.rerun()
        else:
            st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
MODEL = "gemini-3.6-flash"

# (คงส่วน PROMPT, FIELDS, KIND_LABELS, MONTHS และฟังก์ชันต่างๆ ไว้ตามเดิม)
# ... [พี่วางโค้ดส่วนนี้ของเดิมต่อจากนี้ได้เลยครับ] ...

# --- หน้าค้นหา (ที่แก้ไขแล้ว) ---
st.header("ระบบค้นหนังสืออนุมัติ อนุญาตไปราชการ/อนุญาตใช้รถ ที่อนุมัติแล้ว (ปศข.2)")
# ... [ส่วนคำนวณจำนวนเอกสาร] ...

use_date = st.checkbox("ระบุวันที่ไปราชการ / ขอใช้รถ (ถ้าไม่ติ๊ก = ไม่กรองวันที่)")
with st.form("search"):
    kind_label = st.selectbox("ประเภทเอกสาร", ["ทั้งหมด"] + list(KIND_LABELS.values()))
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    rng = None
    if use_date:
        today = datetime.date.today()
        rng = st.date_input("วันที่ (เลือกวันเดียว หรือเลือกเป็นช่วง)", value=(today, today))
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    # ... [โค้ดส่วนการค้นหา rpc ของเดิม] ...
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    
    # 1. ตารางจัดการสถานะดาวน์โหลด (เพิ่มเข้าไปตรงนี้)
    if rows:
        st.subheader("จัดการสถานะการดาวน์โหลด")
        df = pd.DataFrame(rows)
        # แสดงคอลัมน์สำคัญที่ดูง่าย
        edited_df = st.data_editor(
            df[['doc_no', 'subject', 'is_downloaded']],
            column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")},
            use_container_width=True
        )
        if st.button("บันทึกสถานะการดาวน์โหลด"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกเรียบร้อย!")
            st.rerun()
            
    # 2. รายละเอียดเอกสาร (Expander เดิม)
    for r in rows:
        # ... [โค้ดส่วนเดิมของพี่ทั้งหมด] ...
