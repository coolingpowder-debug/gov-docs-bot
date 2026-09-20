import json, datetime, time, uuid, os, mimetypes
import streamlit as st
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ค้นหาหนังสือราชการ", page_icon="📄")

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
doc_no, doc_date, subject, addressee, sender_org, urgency,
travel_start, travel_end, requester_names (รายการชื่อ),
destination_province (ชื่อจังหวัดมาตรฐานเต็ม เช่น กรุงเทพมหานคร),
destination_detail, purpose,
summary (สรุป 1-2 ประโยค), full_text (ถอดข้อความทั้งหมด)
กติกา:
- วันที่ให้ตอบเป็น YYYY-MM-DD โดยใช้ปีตามที่เขียนในเอกสาร (พ.ศ. ก็ใช้ พ.ศ.)
- ถ้าไม่พบข้อมูลหรือไม่ชัดเจน ให้ใส่ null ห้ามเดา
- ตอบเป็น JSON อย่างเดียว"""

FIELDS = ['doc_type', 'doc_no', 'doc_date', 'subject', 'addressee', 'sender_org',
          'urgency', 'travel_start', 'travel_end', 'requester_names',
          'destination_province', 'destination_detail', 'purpose',
          'summary', 'full_text']

MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
          "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def th(d):
    if not d:
        return "-"
    y, m, dd = d.split("-")
    return f"{int(dd)} {MONTHS[int(m) - 1]} {int(y) + 543}"


def retry(fn, tries=6):
    for i in range(tries):
        try:
            return fn()
        except errors.ServerError:
            time.sleep(3 * (i + 1))
    return fn()


def be_to_ce(d):
    if not d:
        return None
    try:
        y, m, dd = d.split('-')
        y = int(y)
        if y > 2400:
            y -= 543
        return f"{y:04d}-{m}-{dd}"
    except Exception:
        return None


def ingest(name, data, mime):
    if sb.table('documents').select('id').eq('file_name', name).execute().data:
        return "ข้าม (มีชื่อไฟล์นี้แล้ว)"
    r = retry(lambda: client.models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0)))
    ex = json.loads(r.text)
    if isinstance(ex, list):
        ex = ex[0]
    for k in ('doc_date', 'travel_start', 'travel_end'):
        ex[k] = be_to_ce(ex.get(k))
    sp = f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}"
    sb.storage.from_('documents').upload(sp, data, {"content-type": mime})
    row = {k: ex.get(k) for k in FIELDS}
    row.update(file_path=sp, file_name=name)
    sb.table('documents').insert(row).execute()
    return f"บันทึกแล้ว | เลขที่ {ex.get('doc_no')}"


def signed(path):
    try:
        res = sb.storage.from_("documents").create_signed_url(path, 3600)
        return res.get("signedURL") or res.get("signedUrl")
    except Exception:
        return None


page = st.radio("เมนู", ["🔎 ค้นหา", "⬆️ อัพโหลดเอกสาร"],
                horizontal=True, label_visibility="collapsed")

if page.startswith("⬆️"):
    st.title("⬆️ อัพโหลดเอกสาร")
    st.caption("รองรับ PDF, JPG, PNG ไฟล์ละไม่เกิน 15 MB แนะนำครั้งละไม่เกิน 5 ไฟล์ "
               "ไฟล์ชื่อซ้ำกับที่มีอยู่แล้วจะถูกข้าม")
    files = st.file_uploader("เลือกไฟล์", accept_multiple_files=True,
                             type=["pdf", "jpg", "jpeg", "png", "webp"])
    if files and st.button("อ่านและบันทึก", type="primary"):
        bar = st.progress(0.0)
        for i, f in enumerate(files):
            data = f.getvalue()
            mime = f.type or mimetypes.guess_type(f.name)[0] or "application/pdf"
            try:
                if len(data) > 15 * 1024 * 1024:
                    msg = "ไฟล์ใหญ่เกิน 15 MB"
                else:
                    with st.spinner(f"กำลังอ่าน {f.name}..."):
                        msg = ingest(f.name, data, mime)
                st.write(f"✅ {f.name} — {msg}")
            except Exception as e:
                if "429" in str(e):
                    st.write(f"❌ {f.name} — โควตา Gemini เต็ม ลองใหม่ภายหลัง")
                else:
                    st.write(f"❌ {f.name} — {str(e)[:120]}")
            bar.progress((i + 1) / len(files))
        st.success("เสร็จแล้ว ไปที่เมนู ค้นหา ได้เลย")
    st.stop()

st.title("🔎 ค้นหาหนังสือราชการ")
with st.form("search"):
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    use_date = st.checkbox("ระบุวันที่ไปราชการ / ขอใช้รถ")
    today = datetime.date.today()
    rng = st.date_input("วันที่ (เลือกวันเดียว หรือเลือกเป็นช่วง)", value=(today, today))
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    d_from = d_to = None
    if use_date:
        if isinstance(rng, (tuple, list)):
            d_from, d_to = rng[0], rng[-1]
        else:
            d_from = d_to = rng
    try:
        rows = sb.rpc("search_documents", {
            "p_org": org.strip() or None,
            "p_name": name.strip() or None,
            "p_province": province.strip() or None,
            "p_from": d_from.isoformat() if d_from else None,
            "p_to": d_to.isoformat() if d_to else None}).execute().data
    except Exception as e:
        st.error(f"ค้นหาไม่สำเร็จ: {str(e)[:120]}")
        rows = []
    st.write(f"พบ {len(rows)} ฉบับ")
    for r in rows:
        title = f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"
        with st.expander(title[:90]):
            st.write(f"**ประเภท:** {r['doc_type'] or '-'}")
            st.write(f"**หน่วยงาน:** {r['sender_org'] or '-'}")
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or []) or '-'}")
            ts, te = r["travel_start"], r["travel_end"]
            st.write("**วันที่:** " + (th(ts) if ts == te else f"{th(ts)} – {th(te)}"))
            place = " ".join(x for x in [r["destination_detail"], r["destination_province"]] if x)
            st.write(f"**สถานที่:** {place or '-'}")
            st.write(f"**วัตถุประสงค์:** {r['purpose'] or '-'}")
            u = signed(r["file_path"])
            if u:
                st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)
