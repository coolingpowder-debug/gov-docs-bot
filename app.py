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

            with st.popover("✏️ แก้ไขชื่อผู้ขอ"):
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
                        st.rerun()
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