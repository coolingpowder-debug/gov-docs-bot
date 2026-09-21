import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

# ... (ส่วนการตั้งค่า st.set_page_config, Login และการเชื่อมต่อ Supabase ให้คงไว้เหมือนเดิมครับ) ...
# (ผมย่อไว้เพื่อให้พี่วางได้สะดวก แต่พี่ไม่ต้องลบของเก่าทิ้งถ้ามันยังทำงานได้ดี)

# [รวมฟังก์ชัน th, retry, be_to_ce, extract, ingest ไว้ที่เดิม]

# --- หน้าค้นหา (ที่ปรับปรุงแล้ว) ---
st.header("ระบบค้นหนังสืออนุมัติ (ปศข.2)")
use_date = st.checkbox("ระบุวันที่ไปราชการ")
with st.form("search"):
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    rng = st.date_input("วันที่", value=None) if use_date else None
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    # [ใส่โค้ด logic การค้นหาแบบเดิมของพี่ตรงนี้]
    # ...
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    if rows:
        df = pd.DataFrame(rows)
        # เพิ่มคอลัมน์สถานะดาวน์โหลดให้แสดงในตารางค้นหา
        edited_df = st.data_editor(
            df[['file_name', 'sender_org', 'destination_province', 'is_downloaded']],
            column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")},
            use_container_width=True
        )
        if st.button("บันทึกสถานะการดาวน์โหลด"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกเรียบร้อย!")
            st.rerun()