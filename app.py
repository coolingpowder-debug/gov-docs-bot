# [ส่วนบนของไฟล์ยังเหมือนเดิมทุกอย่าง ตั้งแต่ import จนถึงหน้า อัปเดต/อัปโหลด]

# ... (ช่วงโค้ดเดิมของพี่ตั้งแต่ import ถึงส่วนก่อน st.header("ระบบค้นหนังสืออนุมัติ..."))

# --- หน้าจอค้นหา (ที่แก้ไขให้มีตารางสถานะแล้ว) ---
st.header("ระบบค้นหนังสืออนุมัติ อนุญาตไปราชการ/อนุญาตใช้รถ ที่อนุมัติแล้ว (ปศข.2)")
# ... (คงโค้ดการแสดงจำนวนเอกสารเดิมของพี่ไว้) ...

use_date = st.checkbox("ระบุวันที่ไปราชการ / ขอใช้รถ (ถ้าไม่ติ๊ก = ไม่กรองวันที่)")
with st.form("search"):
    kind_label = st.selectbox("ประเภทเอกสาร", ["ทั้งหมด"] + list(KIND_LABELS.values()))
    org = st.text_input("หน่วยงาน")
    name = st.text_input("ชื่อ-สกุล")
    province = st.text_input("จังหวัดที่ไป")
    # ... (คงโค้ดการรับค่าวันที่เดิมของพี่ไว้) ...
    go = st.form_submit_button("ค้นหา", type="primary")

if go:
    # ... (โค้ดการเรียก sb.rpc("search_documents", ...) เดิมของพี่) ...
    st.session_state.rows = rows
    st.session_state.searched = True

if st.session_state.get("searched"):
    rows = st.session_state.get("rows", [])
    st.write(f"พบ {len(rows)} ฉบับ")
    
    # --- ส่วนตารางสถานะ (เพิ่มตรงนี้) ---
    if rows:
        df = pd.DataFrame(rows)
        # เลือกเฉพาะคอลัมน์ที่จำเป็น + is_downloaded
        # พี่สามารถเพิ่มชื่อคอลัมน์ใน list นี้ได้ตามต้องการครับ
        display_df = df[['doc_no', 'sender_org', 'requester_names', 'is_downloaded']]
        
        st.write("---")
        st.subheader("จัดการสถานะการดาวน์โหลด")
        edited_df = st.data_editor(
            display_df,
            column_config={
                "is_downloaded": st.column_config.CheckboxColumn("ดาวน์โหลดแล้ว", default=False),
                "requester_names": st.column_config.ListColumn("รายชื่อ")
            },
            use_container_width=True
        )
        
        if st.button("บันทึกสถานะการดาวน์โหลด"):
            # --- ส่วนนี้ต่อท้ายจากส่วนแสดงสถานะการดาวน์โหลดเดิม ---
    
    # ส่วนแสดงรายละเอียดเดิมที่พี่ต้องการ
    for r in rows:
        title = f"{r['doc_no'] or r['file_name']} — {r['subject'] or ''}"
        with st.expander(title[:90]):
            st.write(f"**ประเภท:** {KIND_LABELS.get(r.get('request_kind'), r.get('doc_type') or '-')}")
            st.write(f"**หน่วยงาน:** {r['sender_org'] or '-'}")
            st.write(f"**ผู้ขอ:** {', '.join(r['requester_names'] or []) or '-'}")
            
            with st.expander("✏️ แก้ไขชื่อผู้ขอ"):
                new_names = st.text_area("ชื่อ-สกุลผู้ขอ", value=", ".join(r["requester_names"] or []), key=f"nm_{r['id']}", height=80)
                if st.button("บันทึกชื่อ", key=f"sv_{r['id']}", type="primary"):
                    cleaned = [x.strip() for x in new_names.split(",") if x.strip()]
                    sb.table("documents").update({"requester_names": cleaned}).eq("id", r["id"]).execute()
                    st.success("บันทึกแล้ว")
                    st.rerun()

            ts, te = r["travel_start"], r["travel_end"]
            st.write("**วันที่:** " + (th(ts) if ts == te else f"{th(ts)} – {th(te)}"))
            place = " ".join(x for x in [r["destination_detail"], r["destination_province"]] if x)
            st.write(f"**สถานที่:** {place or '-'}")
            st.write(f"**วัตถุประสงค์:** {r['purpose'] or '-'}")
            if r.get("approved"): st.success("สถานะ: อนุมัติ / อนุญาต แล้ว")
            else: st.warning("สถานะ: ยังไม่พบข้อความ อนุมัติ / อนุญาต ในเอกสารฉบับนี้")
            u = signed(r["file_path"])
            if u: st.link_button("📎 เปิดไฟล์ต้นฉบับ", u)
