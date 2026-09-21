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
            for i, row in edited_df.iterrows():
                sb.table("documents").update({"is_downloaded": row["is_downloaded"]}).eq("id", rows[i]["id"]).execute()
            st.success("บันทึกสถานะเรียบร้อย!")
            st.rerun()
    
    # --- ส่วนแสดงรายละเอียดด้านล่าง (คงเดิม) ---
    for r in rows:
        # ... (โค้ดแสดง expander รายละเอียดเดิมของพี่) ...