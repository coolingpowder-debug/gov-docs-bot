import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

# --- เริ่มต้นไฟล์ ---
st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄")

if "ok" not in st.session_state: st.session_state.ok = False
if not st.session_state.ok:
    pw = st.text_input("รหัสผ่าน", type="password")
    if pw:
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.ok = True
            st.rerun()
        else: st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
MODEL = "gemini-3.6-flash"

# --- ฟังก์ชันช่วยเหลือ (คงเดิมทั้งหมด) ---
# ... (พี่สามารถเก็บฟังก์ชัน th, retry, be_to_ce, extract, ingest, reprocess_missing, signed ของเดิมพี่ไว้ตรงนี้ได้เลยครับ)

# --- หน้าค้นหา ---
st.header("ระบบค้นหนังสืออนุมัติ อนุญาตไปราชการ/อนุญาตใช้รถ ที่อนุมัติแล้ว (ปศข.2)")

use_date = st.checkbox("ระบุวันที่ไปราชการ / ขอใช้รถ (ถ้าไม่ติ๊ก = ไม่กรองวันที่)")
with st.form("search"):
    kind_label = st.selectbox("ประเภทเอกสาร", ["ทั้งหมด"] + list(KIND_LABELS.values()))
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    rng = st.date_input("วันที่ (เลือกวันเดียว หรือเลือกเป็นช่วง)", value=(datetime.date.today(), datetime.date.today())) if use_date else None
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    # ... (ส่วนเรียก rpc เดิมของพี่) ...
    st.session_state.rows = rows
    st.session_state.searched = True

# --- ส่วนตารางสถานะและรายละเอียด ---
if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    
    # 1. ตารางสำหรับติ๊กดาวน์โหลด
    if rows:
        st.subheader("จัดการสถานะการดาวน์โหลด")
        df = pd.DataFrame(rows)
        # สร้างตัวแปร edited_df จากการแก้ในตาราง
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

    # 2. รายละเอียดเอกสาร (Expander)
    for r in rows:
        title = f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"
        with st.expander(title[:90]):
            st.write(f"**หน่วยงาน:** {r['sender_org'] or '-'}")
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or []) or '-'}")
            # ... (โค้ดแสดงรายละเอียดอื่นๆ ของเดิมพี่ทั้งหมด) ...
            u = signed(r["file_path"])
            if u: st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)
