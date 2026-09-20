import json, datetime, time
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

def retry(fn, tries=6):
    for i in range(tries):
        try:
            return fn()
        except errors.ServerError:
            time.sleep(3 * (i + 1))
    return fn()

def signed(path):
    try:
        res = sb.storage.from_("documents").create_signed_url(path, 3600)
        return res.get("signedURL") or res.get("signedUrl")
    except Exception:
        return None

def ask(q):
    today = datetime.date.today().isoformat()
    f = retry(lambda: client.models.generate_content(
        model=MODEL,
        contents=f"""วันนี้คือ {today} แปลงคำถามเป็นตัวกรอง JSON:
province (ชื่อจังหวัดมาตรฐานเต็ม หรือ null),
start และ end (YYYY-MM-DD แบบ ค.ศ. หรือ null),
name (ชื่อหรือนามสกุลผู้ขอ ไม่ต้องมีคำนำหน้า หรือ null)
ถ้าไม่ได้ระบุ ให้ใส่ null ห้ามเดา
คำถาม: {q}""",
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0)))
    flt = json.loads(f.text)
    vec = retry(lambda: client.models.embed_content(
        model="gemini-embedding-001", contents=q,
        config=types.EmbedContentConfig(output_dimensionality=1024))
    ).embeddings[0].values
    rows = sb.rpc("match_documents", {
        "query_embedding": vec, "match_count": 5,
        "p_province": flt.get("province"), "p_start": flt.get("start"),
        "p_end": flt.get("end"), "p_name": flt.get("name")}).execute().data
    ans = retry(lambda: client.models.generate_content(
        model=MODEL,
        contents=f"""ตอบคำถามจากเอกสารด้านล่างเท่านั้น อ้างอิงเลขที่หนังสือ
ตอบเป็นภาษาไทย วันที่ให้แสดงเป็น พ.ศ.
ถ้าไม่มีข้อมูลที่ตอบได้ ให้บอกว่าไม่พบ ห้ามเดา
คำถาม: {q}
เอกสาร: {json.dumps(rows, ensure_ascii=False, default=str)}""")).text
    return flt, rows, ans

st.title("📄 ค้นหาหนังสือราชการ")
if "msgs" not in st.session_state:
    st.session_state.msgs = []

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["text"])
        for s in m.get("src", []):
            st.markdown(f"- [{s['name']}]({s['url']})" if s["url"] else f"- {s['name']}")

q = st.chat_input("ถามได้เลย เช่น ใครไปราชการกรุงเทพเดือนกันยายน")
if q:
    st.session_state.msgs.append({"role": "user", "text": q})
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("กำลังค้นหา..."):
            try:
                flt, rows, ans = ask(q)
            except Exception as e:
                flt, rows, ans = {}, [], f"เกิดข้อผิดพลาด ลองใหม่อีกครั้ง ({str(e)[:80]})"
        st.markdown(ans)
        src = [{"name": r["doc_no"] or r["file_name"], "url": signed(r["file_path"])}
               for r in rows]
        for s in src:
            st.markdown(f"- [{s['name']}]({s['url']})" if s["url"] else f"- {s['name']}")
        with st.expander("ตัวกรองที่ระบบใช้"):
            st.json(flt)
    st.session_state.msgs.append({"role": "assistant", "text": ans, "src": src})
