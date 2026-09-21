import json, datetime, time, uuid, os, mimetypes
import streamlit as st
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
approved (true/false: เป็น true เมื่อในเอกสารมีข้อความสถานะ "อนุมัติ / อนุญาต แล้ว"
  (อาจเขียนว่า "สถานะ อนุมัติ/อนุญาตแล้ว" หรือใกล้เคียง) หรือมีข้อความ ตราประทับ หรือลายมือ
  ของผู้มีอำนาจที่แสดงว่า "อนุมัติ" หรือ "อนุญาต" แล้ว ห้ามนับหัวเรื่องหรือข้อความที่เป็นการ
  "ขออนุมัติ/ขออนุญาต" ถ้าไม่พบหรือไม่แน่ใจ ให้เป็น false),
approval_note (คัดลอกข้อความที่แสดงการอนุมัติ/อนุญาตที่พบสั้นๆ ถ้าไม่พบให้เป็น null),
doc_no, doc_date, subject, addressee, sender_org, urgency,
travel_start, travel_end, requester_names (รายการชื่อ),
destination_province (ชื่อจังหวัดมาตรฐานเต็ม เช่น กรุงเทพมหานคร),
destination_detail, purpose,
summary (สรุป 1-2 ประโยค), full_text (ถอดข้อความทั้งหมด)
กติกา:
- วันที่ให้ตอบเป็น YYYY-MM-DD โดยใช้ปีตามที่เขียนในเอกสาร (พ.ศ. ก็ใช้ พ.ศ.)
- ถ้าไม่พบข้อมูลหรือไม่ชัดเจน ให้ใส่ null ห้ามเดา
- ตอบเป็น JSON อย่างเดียว"""

FIELDS = ['doc_type', 'request_kind', 'approved', 'approval_note', 'doc_no',
          'doc_date', 'subject', 'addressee', 'sender_org', 'urgency',
          'travel_start', 'travel_end', 'requester_names',
          'destination_province', 'destination_detail', 'purpose',
          'summary', 'full_text']

KIND_LABELS = {
    "both": "ขออนุมัติไปราชการและขออนุญาตใช้รถฯ",
    "trip": "ขออนุมัติไปราชการ (ไม่ขออนุญาตใช้รถฯ)",
    "vehicle": "ขออนุญาตใช้รถฯ",
}

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


def extract(data, mime):
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
    if ex.get('request_kind') not in KIND_LABELS:
        ex['request_kind'] = None
    ex['approved'] = bool(ex.get('approved'))
    return ex


def ingest(name, data, mime, overwrite=False):
    found = sb.table('documents').select('id').eq('file_name', name).execute().data
    if found and not overwrite:
        return "ข้าม (มีชื่อไฟล์นี้แล้ว)"
    ex = extract(data, mime)
    sp = f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}"
    sb.storage.from_('documents').upload(sp, data, {"content-type": mime})
    row = {k: ex.get(k) for k in FIELDS}
    row.update(file_path=sp, file_name=name)
    if found:
        sb.table('documents').update(row).eq('id', found[0]['id']).execute()
        return f"อัปเดตแล้ว | เลขที่ {ex.get('doc_no')}"
    sb.table('documents').insert(row).execute()
    return f"บันทึกแล้ว | เลขที่ {ex.get('doc_no')}"


def reprocess_missing(limit=10):
    rows = (sb.table('documents').select('id,file_name,file_path')
            .is_('request_kind', 'null').limit(limit).execute().data)
    out = []
    for r in rows:
        try:
            data = sb.storage.from_('documents').download(r['file_path'])
            mime = mimetypes.guess_type(r['file_path'])[0] or 'application/pdf'
            ex = extract(data, mime)
            sb.table('documents').update({k: ex.get(k) for k in FIELDS}) \
                .eq('id', r['id']).execute()
            out.append(f"✅ {r['file_name']} — {KIND_LABELS.get(ex.get('request_kind'), 'อื่นๆ')}"
                       f" | {'อนุมัติแล้ว' if ex.get('approved') else 'ยังไม่พบข้อความอนุมัติ'}")
        except Exception as e:
            if "429" in str(e):
                out.append(f"❌ {r['file_name']} — โควตา Gemini เต็ม ลองใหม่ภายหลัง")
                break
            out.append(f"❌ {r['file_name']} — {str(e)[:100]}")
    return out


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
    st.caption("รองรับ PDF, JPG, PNG ไฟล์ละไม่เกิน 15 MB แนะนำครั้งละไม่เกิน 5 ไฟล์")
    files = st.file_uploader("เลือกไฟล์", accept_multiple_files=True,
                             type=["pdf", "jpg", "jpeg", "png", "webp"])
    overwrite = st.checkbox("ถ้าชื่อไฟล์ซ้ำกับที่มีอยู่ ให้อ่านใหม่และอัปเดตทับ")
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
                        msg = ingest(f.name, data, mime, overwrite)
                st.write(f"✅ {f.name} — {msg}")
            except Exception as e:
                if "429" in str(e):
                    st.write(f"❌ {f.name} — โควตา Gemini เต็ม ลองใหม่ภายหลัง")
                else:
                    st.write(f"❌ {f.name} — {str(e)[:120]}")
            bar.progress((i + 1) / len(files))
        st.success("เสร็จแล้ว ไปที่เมนู ค้นหา ได้เลย")

    st.divider()
    with st.expander("🔄 อ่านซ้ำเอกสารเดิมที่ยังไม่มีข้อมูลประเภท/สถานะ"):
        st.caption("ใช้กับเอกสารที่อัพโหลดไว้ก่อนเพิ่มตัวกรองประเภท/สถานะ "
                   "ระบบจะดึงไฟล์เดิมมาอ่านใหม่ ครั้งละไม่เกิน 10 ฉบับ")
        if st.button("เริ่มอ่านซ้ำ"):
            with st.spinner("กำลังอ่านซ้ำ..."):
                res = reprocess_missing()
            if not res:
                st.info("ไม่มีเอกสารที่ต้องอ่านซ้ำ")
            for line in res:
                st.write(line)
    st.stop()

st.header("ระบบค้นหนังสืออนุมัติ อนุญาตไปราชการ/อนุญาตใช้รถ ที่อนุมัติแล้ว (ปศข.2)")
try:
    total = sb.table('documents').select('id', count='exact').limit(1).execute().count
    st.caption(f"เอกสารในระบบทั้งหมด {total} ฉบับ")
except Exception:
    pass

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
    d_from = d_to = None
    if use_date and rng:
        if isinstance(rng, (tuple, list)):
            if len(rng) > 0:
                d_from, d_to = rng[0], rng[-1]
        else:
            d_from = d_to = rng
    kind = next((k for k, v in KIND_LABELS.items() if v == kind_label), None)
    try:
        rows = sb.rpc("search_documents", {
            "p_org": org.strip() or None,
            "p_name": name.strip() or None,
            "p_province": province.strip() or None,
            "p_from": d_from.isoformat() if d_from else None,
            "p_to": d_to.isoformat() if d_to else None,
            "p_kind": kind}).execute().data
    except Exception as e:
        st.error(f"ค้นหาไม่สำเร็จ: {str(e)[:120]}")
        rows = []
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    if not rows:
        st.info("ไม่พบเอกสาร ลองลดเงื่อนไขลง เช่น ค้นด้วยชื่อหรือนามสกุลอย่างเดียว "
                "ตัวสะกดต้องตรงกับในเอกสาร หรือลองพิมพ์แค่บางส่วนของชื่อ")
    for r in rows:
        title = f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"
        with st.expander(title[:90]):
            st.write(f"**ประเภท:** {KIND_LABELS.get(r.get('request_kind'), r.get('doc_type') or '-')}")
            st.write(f"**หน่วยงาน:** {r['sender_org'] or '-'}")
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or []) or '-'}")

            with st.expander("✏️ แก้ไขชื่อผู้ขอ"):
                st.caption("ถ้าระบบอ่านชื่อจากเอกสารสแกนผิด แก้ที่นี่ได้ "
                           "หลายชื่อให้คั่นด้วยเครื่องหมายจุลภาค ( , )")
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
