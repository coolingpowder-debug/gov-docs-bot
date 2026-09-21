import json, datetime, time, uuid, os, mimetypes
import streamlit as st
import pandas as pd
from google import genai
from google.genai import types, errors
from supabase import create_client

st.set_page_config(page_title="ระบบค้นหนังสืออนุมัติ (ปศข.2)", page_icon="📄", layout="wide")

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

# --- Constants & Helpers ---
PROMPT = """คุณคือระบบอ่านหนังสือราชการไทยที่สแกนมา เอกสาร 1 ไฟล์อาจมีหลายเรื่อง (หลายคำสั่ง/หลายรายการ) ให้แยกวิเคราะห์ออกเป็นรายการย่อยๆ เป็นรูปแบบ JSON Array ของ Object ตามคีย์ต่อไปนี้: 
[
  {"doc_type": "...", "request_kind": "...", "approved": true/false, "approval_note": "...", "doc_no": "...", "doc_date": "YYYY-MM-DD", "subject": "...", "addressee": "...", "sender_org": "...", "urgency": "...", "travel_start": "YYYY-MM-DD", "travel_end": "YYYY-MM-DD", "requester_names": ["ชื่อ1", "ชื่อ2"], "destination_province": "...", "destination_detail": "...", "purpose": "...", "summary": "...", "full_text": "..."}
]
กติกา: หากมีหลายเรื่องในไฟล์เดียว ให้แตกเป็นหลาย Object ใน Array, วันที่ YYYY-MM-DD, ไม่พบใส่ null, ตอบเป็น JSON Array เท่านั้น"""

FIELDS = ['doc_type', 'request_kind', 'approved', 'approval_note', 'doc_no', 'doc_date', 'subject', 'addressee', 'sender_org', 'urgency', 'travel_start', 'travel_end', 'requester_names', 'destination_province', 'destination_detail', 'purpose', 'summary', 'full_text']
KIND_LABELS = {"both": "ขออนุมัติไปราชการและขออนุญาตใช้รถฯ", "trip": "ขออนุมัติไปราชการ (ไม่ขออนุญาตใช้รถฯ)", "vehicle": "ขออนุญาตใช้รถฯ"}
MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

def th(d):
    if not d: return "-"
    try:
        y, m, dd = d.split("-")
        return f"{int(dd)} {MONTHS[int(m) - 1]} {int(y) + 543}"
    except: return d

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

def extract_multiple(data, mime):
    r = retry(lambda: client.models.generate_content(model=MODEL, contents=[types.Part.from_bytes(data=data, mime_type=mime), PROMPT], config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0)))
    text = r.text.strip()
    if text.startswith("```json"): text = text[7:]
    if text.endswith("```"): text = text[:-3]
    exs = json.loads(text.strip())
    if isinstance(exs, dict): exs = [exs]
    
    cleaned_list = []
    for ex in exs:
        for k in ('doc_date', 'travel_start', 'travel_end'): 
            ex[k] = be_to_ce(ex.get(k))
        ex['approved'] = bool(ex.get('approved'))
        cleaned_list.append(ex)
    return cleaned_list

def ingest(name, data, mime, overwrite=False):
    found_files = sb.table('documents').select('file_path').eq('file_name', name).execute().data
    if found_files and not overwrite: 
        return "ข้าม (มีชื่อไฟล์นี้แล้ว)"
    
    sp = f"{uuid.uuid4()}{os.path.splitext(name)[1].lower()}"
    sb.storage.from_('documents').upload(sp, data, {"content-type": mime})
    
    items = extract_multiple(data, mime)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    count = 0
    for ex in items:
        row = {k: ex.get(k) for k in FIELDS if k in ex}
        row.update(file_path=sp, file_name=name, is_downloaded=False, created_at=now_str)
        sb.table('documents').insert(row).execute()
        count += 1
        
    return f"บันทึกสำเร็จ แยกได้ {count} รายการ"

def signed(path):
    try:
        res = sb.storage.from_("documents").create_signed_url(path, 3600)
        return res.get("signedURL") or res.get("signedUrl")
    except: return None

# --- Navigation Menu ---
page = st.radio("เมนู", ["📊 แดชบอร์ดภาพรวม", "🔎 ค้นหาเอกสาร", "⬆️ อัพโหลดเอกสาร"], horizontal=True)
st.divider()

# --- 1. หน้าแดชบอร์ดภาพรวม (20 รายการล่าสุด) ---
if page.startswith("📊"):
    st.subheader("📈 แดชบอร์ดข้อมูลการอนุมัติล่าสุด (20 รายการล่าสุด)")
    
    try:
        res = sb.table('documents').select('*').eq('approved', True).order('created_at', desc=True).limit(20).execute()
        d_rows = res.data or []
    except Exception:
        # กรณีฐานข้อมูลยังไม่มีคอลัมน์ created_at ให้ดึงแบบธรรมดาก่อนกันพัง
        res = sb.table('documents').select('*').eq('approved', True).limit(20).execute()
        d_rows = res.data or []

    if not d_rows:
        st.info("ยังไม่มีข้อมูลเอกสารที่อนุมัติในระบบ")
    else:
        table_data = []
        for idx, r in enumerate(d_rows, 1):
            c_at = r.get('created_at', '')
            try:
                dt_obj = datetime.datetime.strptime(c_at[:19], "%Y-%m-%d %H:%M:%S")
                formatted_created = f"{dt_obj.strftime('%d')} {MONTHS[dt_obj.month - 1]} {dt_obj.year + 543} {dt_obj.strftime('%H:%M')}"
            except:
                formatted_created = c_at or "-"
                
            req_names = ", ".join(r.get('requester_names') or []) or "-"
            org_dest = r.get('sender_org') or "-"
            prov = r.get('destination_province') or "-"
            
            ts, te = r.get('travel_start'), r.get('travel_end')
            date_single = th(ts)
            if ts and te and ts != te:
                date_range = f"{th(ts)} - {th(te)}"
            else:
                date_range = th(ts)
                
            table_data.append({
                "ลำดับ": idx,
                "วันที่Adminอัพโหลด": formatted_created,
                "ชื่อผู้ขอไปราชการ/ขอใช้รถ": req_names,
                "หน่วยงานปลายทางที่ไป": org_dest,
                "จังหวัดที่ไป": prov,
                "วันที่ไป": date_single,
                "ว.ด.ป. - ว.ด.ป.ที่": date_range,
                "สถานะอนุมัติ": "🟩 อนุมัติแล้ว"
            })
            
        df_dash = pd.DataFrame(table_data)
        st.dataframe(df_dash, use_container_width=True, hide_index=True)

# --- 2. หน้าอัพโหลดเอกสาร ---
elif page.startswith("⬆️"):
    st.title("⬆️ อัพโหลดเอกสาร (รองรับแยกหลายรายการใน 1 ไฟล์)")
    files = st.file_uploader("เลือกไฟล์ PDF หรือรูปภาพ", accept_multiple_files=True, type=["pdf", "jpg", "jpeg", "png", "webp"])
    overwrite = st.checkbox("อัปเดตทับหากชื่อไฟล์ซ้ำ")
    if files and st.button("อ่านและบันทึกเข้าสู่ระบบ", type="primary"):
        with st.spinner("AI กำลังอ่านและแยกแยะรายการเอกสาร กรุณารอสักครู่..."):
            for f in files:
                msg = ingest(f.name, f.getvalue(), f.type or "application/pdf", overwrite)
                st.write(f"✅ **{f.name}** — {msg}")
        st.success("ประมวลผลเสร็จสิ้นทุกไฟล์แล้วครับ!")

# --- 3. หน้าค้นหาเอกสาร ---
else:
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
        
        try:
            res = sb.rpc("search_documents", {"p_org": org.strip() or None, "p_name": name.strip() or None, "p_province": province.strip() or None, "p_from": d_from, "p_to": d_to, "p_kind": kind}).execute()
            st.session_state.rows = res.data or []
            st.session_state.searched = True
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการค้นหา: {e}")

    if st.session_state.get("searched"):
        rows = st.session_state.get("rows", [])
        st.write(f"พบผลลัพธ์ทั้งหมด {len(rows)} รายการ")
        
        if rows:
            st.subheader("จัดการสถานะการดาวน์โหลด")
            df = pd.DataFrame(rows)
            if 'is_downloaded' not in df.columns:
                df['is_downloaded'] = False
            cols_to_show = [c for c in ['file_name', 'subject', 'is_downloaded'] if c in df.columns]
            
            edited_df = st.data_editor(
                df[cols_to_show], 
                column_config={"is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว")}, 
                use_container_width=True
            )
            
            if st.button("บันทึกสถานะการดาวน์โหลด"):
                for i, row in edited_df.iterrows():
                    sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
                st.success("บันทึกสถานะเรียบร้อย!")
                st.rerun()

        for r in rows:
            title = f"{r.get('file_name', 'เอกสาร')} — {r.get('subject') or ''}"
            with st.expander(title[:90]):
                st.write(f"**ประเภท:** {KIND_LABELS.get(r.get('request_kind'), r.get('doc_type') or '-')}")
                st.write(f"**หน่วยงาน:** {r.get('sender_org') or '-'}")
                st.write(f"**ผู้ขอ:** {', '.join(r.get('requester_names') or []) or '-'}")
                
                ts, te = r.get("travel_start"), r.get("travel_end")
                st.write("**วันที่ไป:** " + (th(ts) if ts == te else f"{th(ts)} – {th(te)}"))
                place = " ".join(x for x in [r.get("destination_detail"), r.get("destination_province")] if x)
                st.write(f"**สถานที่:** {place or '-'}")
                st.write(f"**วัตถุประสงค์:** {r.get('purpose') or '-'}")
                
                if r.get("approved"): 
                    st.success("สถานะ: อนุมัติ / อนุญาต แล้ว 🟩")
                else: 
                    st.warning("สถานะ: ยังไม่พบข้อความ อนุมัติ / อนุญาต ในเอกสารฉบับนี้")
                    
                u = signed(r.get("file_path"))
                if u: 
                    st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)
