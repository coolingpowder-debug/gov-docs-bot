import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

# ... (ส่วนการตั้งค่า st.set_page_config, Login และการเชื่อมต่อ Supabase พี่คงไว้เหมือนเดิมนะครับ) ...
# [ตรงนี้พี่เก็บโค้ดส่วนต้นของพี่ไว้เหมือนเดิมทุกอย่าง]

# --- โค้ดส่วนท้ายหน้าค้นหา (วางต่อจากส่วน if go: ที่พี่มีอยู่) ---

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    if not rows:
        st.info("ไม่พบเอกสาร ลองลดเงื่อนไขลง")
    
    # --- ตารางสถานะดาวน์โหลด (เพิ่มตรงนี้) ---
    if rows:
        st.write("---")
        st.subheader("จัดการสถานะการดาวน์โหลด")
        df = pd.DataFrame(rows)
        # เลือกคอลัมน์ที่จะแสดงในตาราง
        display_df = df[['doc_no', 'sender_org', 'is_downloaded']]
        edited_df = st.data_editor(
            display_df,
            column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว", default=False)},
            use_container_width=True
        )
        if st.button("บันทึกสถานะการดาวน์โหลด"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกเรียบร้อย!")
            st.rerun()
    # --- จบส่วนตาราง ---

    # --- ส่วนแสดง Expander รายละเอียดเดิมของพี่ (ต้องอยู่ใต้ if st.session_state.get("searched"): เพื่อให้รันในบล็อกเดียวกัน) ---
    for r in rows:
        title = f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"
        with st.expander(title[:90]):
            st.write(f"**ประเภท:** {KIND_LABELS.get(r.get('request_kind'), r.get('doc_type') or '-')}")
            st.write(f"**หน่วยงาน:** {r['sender_org'] or '-'}")
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or []) or '-'}")

            with st.expander("✏️ แก้ไขชื่อผู้ขอ"):
                st.caption("หลายชื่อให้คั่นด้วยเครื่องหมายจุลภาค ( , )")
                new_names = st.text_area(
                    "ชื่อ-สกุลผู้ขอ",
                    value=", ".join(r["requester_names"] or []),
                    key=f"nm_{r['id']}", height=80)
                if st.button("บันทึกชื่อ", key=f"sv_{r['id']}", type="primary"):
                    cleaned = [x.strip() for x in new_names.split(",") if x.strip()]
                    try:
                        sb.table("documents").update(
                            {"requester_names": cleaned}).eq("id", r["id"]).execute()
                        r["requester_names"] = cleaned
                        st.success("บันทึกแล้ว")
                    except Exception as e:
                        st.error(f"บันทึกไม่สำเร็จ: {str(e)[:120]}")

            ts, te = r["travel_start"], r["travel_end"]
            st.write("**วันที่:** " + (th(ts) if ts == te else f"{th(ts)} – {th(te)}"))
            place = " ".join(x for x in [r["destination_detail"], r["destination_province"]] if x)
            st.write(f"**สถานที่:** {place or '-'}")
            st.write(f"**วัตถุประสงค์:** {r['purpose'] or '-'}")
            if r.get("approved"):
                st.success("สถานะ: อนุมัติ / อนุญาต แล้ว")
            else:
                st.warning("สถานะ: ยังไม่พบข้อความ อนุมัติ / อนุญาต ในเอกสารฉบับนี้")
            u = signed(r["file_path"])
            if u:
                st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)