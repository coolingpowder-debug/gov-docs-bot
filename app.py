import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄")

# --- ระบบ Login ---
if "ok" not in st.session_state: st.session_state.ok = False
if not st.session_state.ok:
    pw = st.text_input("รหัสผ่าน", type="password")
    if pw and pw == st.secrets["APP_PASSWORD"]:
        st.session_state.ok = True
        st.rerun()
    elif pw: st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()

# --- เชื่อมต่อฐานข้อมูล ---
sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
MODEL = "gemini-3.6-flash"

# --- คำสั่ง AI ---
PROMPT = """คุณคือระบบอ่านหนังสือราชการไทย ดึงข้อมูล JSON:
doc_type, request_kind (both, trip, vehicle, null), approved (true/false),
approval_note, doc_no, doc_date, subject, sender_org,
travel_start, travel_end, requester_names (list),
destination_province, purpose
กติกา: วันที่ YYYY-MM-DD, ข้อมูลไม่พบให้ null, ตอบเป็น JSON เท่านั้น"""

FIELDS = ['doc_type', 'request_kind', 'approved', 'approval_note', 'doc_no',
          'doc_date', 'subject', 'sender_org', 'travel_start', 'travel_end', 
          'requester_names', 'destination_province', 'purpose', 'is_downloaded']

# --- ฟังก์ชันช่วยเหลือ ---
def be_to_ce(d):
    if not d: return None
    try:
        y, m, dd = d.split('-')
        y = int(y)
        if y > 2400: y -= 543
        return f"{y:04d}-{m}-{dd}"
    except: return None

def extract(data, mime):
    r = client.models.generate_content(model=MODEL, contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0))
    ex = json.loads(r.text)
    if isinstance(ex, list): ex = ex[0]
    for k in ('doc_date', 'travel_start', 'travel_end'): ex[k] = be_to_ce(ex.get(k))
    ex['approved'] = bool(ex.get('approved'))
    return ex

def ingest(name, data, mime):
    ex = extract(data, mime)
    sp = f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}"
    sb.storage.from_('documents').upload(sp, data, {"content-type": mime})
    row = {k: ex.get(k) for k in FIELDS if k != 'is_downloaded'}
    row.update(file_path=sp, file_name=name, is_downloaded=False)
    sb.table('documents').insert(row).execute()
    return f"บันทึกแล้ว: {ex.get('doc_no', name)}"

# --- หน้าจอหลัก ---
page = st.radio("เมนู", ["🔎 ค้นหา", "⬆️ อัพโหลดเอกสาร"], horizontal=True, label_visibility="collapsed")

if page == "⬆️ อัพโหลดเอกสาร":
    st.title("⬆️ อัพโหลดเอกสาร")
    files = st.file_uploader("เลือกไฟล์", accept_multiple_files=True, type=["pdf", "jpg", "png"])
    if files and st.button("บันทึกเข้าระบบ"):
        for f in files:
            try:
                msg = ingest(f.name, f.getvalue(), f.type)
                st.write(f"✅ {f.name} — {msg}")
            except Exception as e: st.error(f"เกิดข้อผิดพลาดกับ {f.name}: {e}")

else:
    st.header("🔎 ค้นหาเอกสาร")
    name_query = st.text_input("ชื่อผู้ขอ หรือ ชื่อไฟล์")
    if st.button("ค้นหา"):
        res = sb.table("documents").select("*").ilike("file_name", f"%{name_query}%").execute()
        st.session_state.rows = res.data

    if "rows" in st.session_state and st.session_state.rows:
        df = pd.DataFrame(st.session_state.rows)
        # แสดงตารางให้กดติ๊กสถานะ
        edited_df = st.data_editor(
            df[['file_name', 'sender_org', 'is_downloaded']],
            column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")},
            use_container_width=True
        )
        if st.button("บันทึกสถานะ"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", st.session_state.rows[i]["id"]).execute()
            st.success("อัปเดตสถานะเรียบร้อย!")
            st.rerun()