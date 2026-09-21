import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄")

# --- Login & Connect ---
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

# --- ฟังก์ชันช่วยเหลือเดิมของพี่ ---
PROMPT = """คุณคือระบบอ่านหนังสือราชการไทยที่สแกนมา ดึงข้อมูลเป็น JSON ตามคีย์ต่อไปนี้: doc_type, request_kind, approved, approval_note, doc_no, doc_date, subject, addressee, sender_org, urgency, travel_start, travel_end, requester_names, destination_province, destination_detail, purpose, summary, full_text. กติกา: วันที่ YYYY-MM-DD, ไม่พบใส่ null, ตอบเป็น JSON อย่างเดียว"""
FIELDS = ['doc_type', 'request_kind', 'approved', 'approval_note', 'doc_no', 'doc_date', 'subject', 'addressee', 'sender_org', 'urgency', 'travel_start', 'travel_end', 'requester_names', 'destination_province', 'destination_detail', 'purpose', 'summary', 'full_text']
KIND_LABELS = {"both": "ขออนุมัติไปราชการและขออนุญาตใช้รถฯ", "trip": "ขออนุมัติไปราชการ (ไม่ขออนุญาตใช้รถฯ)", "vehicle": "ขออนุญาตใช้รถฯ"}
MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

def th(d):
    if not d: return "-"
    y, m, dd = d.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {int(y) + 543}"

def be_to_ce(d):
    if not d: return None
    try:
        y, m, dd = d.split('-')
        y = int(y)
        if y > 2400: y -= 543
        return f"{y:04d}-{m}-{dd}"
    except: return None

def retry(fn, tries=6):
    for i in range(tries):
        try: return fn()
        except errors.ServerError: time.sleep(3 * (i + 1))
    return fn()

def extract(data, mime):
    r = retry(lambda: client.models.generate_content(model=MODEL, contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT], config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0)))
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
    row = {k: ex.get(k) for k in FIELDS}
    row.update(file_path=sp, file_name=name, is_downloaded=False)
    if found:
        sb.table('documents').update(row).eq('id', found[0]['id']).execute()
        return f"อัปเดตแล้ว | เลขที่ {ex.get('doc_no')}"
    sb.table('documents').insert(row).execute()
    return f"บันทึกแล้ว | เลขที่ {ex.get('doc_no')}"

def signed(path):
    try:
        res = sb.storage.from_("documents").create_signed_url(path, 3600)
        return res.get("signedURL") or res.get("signedUrl")
    except: return None

# --- หน้าจอหลัก ---
page = st.radio("เมนู", ["🔎 ค้นหา", "⬆️ อัพโหลดเอกสาร"], horizontal=True, label_visibility="collapsed")

if page.startswith("⬆️"):
    st.title("⬆️ อัพโหลดเอกสาร")
    files = st.file_uploader("เลือกไฟล์", accept_multiple_files=True, type=["pdf", "jpg", "jpeg", "png", "webp"])
    overwrite = st.checkbox("ถ้าชื่อไฟล์ซ้ำกับที่มีอยู่ ให้อ่านใหม่และอัปเดตทับ")
    if files and st.button("อ่านและบันทึก", type="primary"):
        for f in files:
            msg = ingest(f.name, f.getvalue(), f.type or "application/pdf", overwrite)
            st.write(f"✅ {f.name} — {msg}")
    st.stop()

# --- หน้าค้นหา ---
st.header("ระบบค้นหนังสืออนุมัติฯ (ปศข.2)")
use_date = st.checkbox("ระบุวันที่ไปราชการ / ขอใช้รถ (ถ้าไม่ติ๊ก = ไม่กรองวันที่)")
with st.form("search"):
    kind_label = st.selectbox("ประเภทเอกสาร", ["ทั้งหมด"] + list(KIND_LABELS.values()))
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    rng = st.date_input("วันที่ (เลือกวันเดียว หรือเลือกเป็นช่วง)", value=(datetime.date.today(), datetime.date.today())) if use_date else None
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    d_from = d_to = rng[0].isoformat() if isinstance(rng, tuple) else (rng.isoformat() if rng else None)
    if isinstance(rng, tuple): d_to = rng[1].isoformat()
    kind = next((k for k, v in KIND_LABELS.items() if v == kind_label), None)
    rows = sb.rpc("search_documents", {"p_org": org.strip() or None, "p_name": name.strip() or None, "p_province": province.strip() or None, "p_from": d_from, "p_to": d_to, "p_kind": kind}).execute().data
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    if rows:
        st.subheader("จัดการสถานะการดาวน์โหลด")
        df = pd.DataFrame(rows)
        
        # ตรวจสอบว่ามีคอลัมน์ is_downloaded หรือยัง ถ้าไม่มีให้สร้างเป็น False
        if 'is_downloaded' not in df.columns:
            df['is_downloaded'] = False
            
        # เลือกคอลัมน์เฉพาะที่มีอยู่จริง
        cols_to_show = [c for c in ['doc_no', 'subject', 'is_downloaded'] if c in df.columns]
        
        edited_df = st.data_editor(
            df[cols_to_show], 
            column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")}, 
            use_container_width=True
        )
        
        if st.button("บันทึกสถานะการดาวน์โหลด"):
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกเรียบร้อย!")
            st.rerun()

    for r in rows:
        with st.expander(f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"):
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or [])}")
            # ... (ที่เหลือของเดิมพี่)
            u = signed(r["file_path"])
            if u: st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)
