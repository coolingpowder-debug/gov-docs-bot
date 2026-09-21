import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄")

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

PROMPT = """คุณคือระบบอ่านหนังสือราชการไทยที่สแกนมา
ดึงข้อมูลเป็น JSON ตามคีย์ต่อไปนี้เท่านั้น:
doc_type (เลือกจาก: ขออนุมัติไปราชการ, ขออนุญาตใช้รถ, อื่นๆ),
request_kind (ใช้ค่าใดค่าหนึ่งเท่านั้น:
  "both" = เอกสารขออนุมัติไปราชการ และขออนุญาตใช้รถ ในฉบับเดียวกัน,
  "trip" = ขออนุมัติไปราชการอย่างเดียว ไม่ได้ขออนุญาตใช้รถ,
  "vehicle" = ขออนุญาตใช้รถอย่างเดียว,
  null = เอกสารประเภทอื่น),
approved (true/false: เป็น true เมื่อในเอกสารมีข้อความสถานะ "อนุมัติ / อนุญาต แล้ว"),
approval_note, doc_no, doc_date, subject, addressee, sender_org, urgency,
travel_start, travel_end, requester_names (รายการชื่อ),
destination_province, destination_detail, purpose,
summary, full_text
กติกา: วันที่ให้ตอบเป็น YYYY-MM-DD. ไม่พบให้ใส่ null. ตอบเป็น JSON อย่างเดียว"""

FIELDS = ['doc_type', 'request_kind', 'approved', 'approval_note', 'doc_no',
          'doc_date', 'subject', 'addressee', 'sender_org', 'urgency',
          'travel_start', 'travel_end', 'requester_names',
          'destination_province', 'destination_detail', 'purpose',
          'summary', 'full_text', 'is_downloaded']

KIND_LABELS = {
    "both": "ขออนุมัติไปราชการและขออนุญาตใช้รถฯ",
    "trip": "ขออนุมัติไปราชการ (ไม่ขออนุญาตใช้รถฯ)",
    "vehicle": "ขออนุญาตใช้รถฯ",
}

MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
          "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

def th(d):
    if not d: return "-"
    y, m, dd = d.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {int(y) + 543}"

def retry(fn, tries=6):
    for i in range(tries):
        try: return fn()
        except errors.ServerError: time.sleep(3 * (i + 1))
    return fn()

def be_to_ce(d):
    if not d: return None
    try:
        y, m, dd = d.split('-')
        y = int(y)
        if y > 2400: y -= 543
        return f"{y:04d}-{m}-{dd}"
    except: return None

def extract(data, mime):
    r = retry(lambda: client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0)))
    ex = json.loads(r.text)
    if isinstance(ex, list): ex = ex[0]
    for k in ('doc_date', 'travel_start', 'travel_end'): ex[k] = be_to_ce(ex.get(k))
    ex['approved'] = bool(ex.get('approved'))
    return ex

def ingest(name, data, mime, overwrite=False):
    found = sb.table('documents').select('id').eq('file_name', name).execute().data
    if found and not overwrite: return "ข้าม (มีชื่อไฟล์นี้แล้ว)"
    ex = extract(data, mime)
    sp = f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}"
    sb.storage.from_('documents').upload(sp, data, {"content-type": mime})
    row = {k: ex.get(k) for k in FIELDS if k != 'is_downloaded'}
    row.update(file_path=sp, file_name=name, is_downloaded=False)
    if found:
        sb.table('documents').update(row).eq('id', found[0]['id']).execute()
        return f"อัปเดตแล้ว | เลขที่ {ex.get('doc_no')}"
    sb.table('documents').insert(row).execute()
    return f"บันทึกแล้ว | เลขที่ {ex.get('doc_no')}"

# --- หน้าเว็บ ---
page = st.radio("เมนู", ["🔎 ค้นหา", "⬆️ อัพโหลดเอกสาร"], horizontal=True, label_visibility="collapsed")

if page.startswith("⬆️"):
    st.title("⬆️ อัพโหลดเอกสาร")
    files = st.file_uploader("เลือกไฟล์", accept_multiple_files=True, type=["pdf", "jpg", "jpeg", "png", "webp"])
    if files and st.button("อ่านและบันทึก", type="primary"):
        for f in files:
            msg = ingest(f.name, f.getvalue(), f.type, True)
            st.write(f"✅ {f.name} — {msg}")
    st.stop()

st.header("ระบบค้นหนังสืออนุมัติฯ (ปศข.2)")
use_date = st.checkbox("ระบุวันที่ไปราชการ")
with st.form("search"):
    kind_label = st.selectbox("ประเภทเอกสาร", ["ทั้งหมด"] + list(KIND_LABELS.values()))
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    kind = next((k for k, v in KIND_LABELS.items() if v == kind_label), None)
    rows = sb.rpc("search_documents", {"p_org": org.strip() or None, "p_name": name.strip() or None, "p_kind": kind}).execute().data
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    if rows:
        df = pd.DataFrame(rows)
        st.write("จัดการสถานะการดาวน์โหลดในตารางด้านล่าง:")
        edited_df = st.data_editor(df[['file_name', 'sender_org', 'is_downloaded']], 
                                   column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")},
                                   use_container_width=True)
        if st.button("บันทึกการดาวน์โหลด"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกเรียบร้อย!")
            st.rerun()
