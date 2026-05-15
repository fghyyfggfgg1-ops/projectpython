import streamlit as st
import fitz  # PyMuPDF
from docx import Document
import random
import re
import pandas as pd
import io
import time
import os
import qrcode
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- 1. إعدادات الصفحة والتنسيق البصري (CSS) ---
st.set_page_config(page_title="المساعد الذكي | Smart Assistant", page_icon="🎓", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700&display=swap');
    html, body, [data-testid="stAppViewContainer"], .main {
        font-family: 'Cairo', sans-serif;
        direction: rtl !important;
        text-align: right !important;
    }
    .stMarkdown, .stTextArea, .stTextInput, .stRadio, .stSelectbox, p, h1, h2, h3, label {
        direction: rtl !important;
        text-align: right !important;
    }
    .question-card {
        background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 12px;
        padding: 25px; margin-bottom: 20px; border-right: 8px solid #1e3a8a;
    }
    .stButton > button {
        border-radius: 10px; background-color: #1E3A8A !important; color: white !important;
        width: 100%; height: 45px; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. وظائف النظام الأساسية ---

def save_to_permanent_excel(student_info, exam_details, final_score):
    file_path = "permanent_results.xlsx"
    flat_data = []
    for q in exam_details:
        flat_data.append({
            "الاسم": student_info['name'],
            "رقم القيد": student_info['id'],
            "السؤال": q['q_text'],
            "إجابة الطالب": q['student_ans'],
            "الإجابة النموذجية": q['correct_ans'],
            "الدرجة": q['q_score'],
            "النتيجة النهائية": final_score,
            "التاريخ": time.strftime("%Y-%m-%d %H:%M")
        })
    df_new = pd.DataFrame(flat_data)
    try:
        if not os.path.isfile(file_path):
            df_new.to_excel(file_path, index=False)
        else:
            existing_df = pd.read_excel(file_path)
            pd.concat([existing_df, df_new], ignore_index=True).to_excel(file_path, index=False)
    except:
        st.error("يرجى إغلاق ملف الإكسل لتحديث النتائج.")

def reformulate_question(original_text, new_type):
    clean = re.sub(r'^(ناقش بالتفصيل المفهوم التالي:|اختر الإجابة الصحيحة:|هل تعتبر العبارة صحيحة:|هل العبارة التالية صحيحة:)', '', original_text).strip(" ؟")
    if new_type == "مقالي":
        return f"ناقش بالتفصيل المفهوم التالي: {clean}"
    elif new_type == "صح_خطأ":
        return f"هل العبارة التالية صحيحة: {clean}؟"
    elif new_type == "اختياري":
        return f"اختر الإجابة الصحيحة المتعلقة بـ: {clean}..."
    return original_text

def calculate_smart_score(student_ans, model_ans):
    if not student_ans or len(str(student_ans).strip()) < 2: 
        return 0
    try:
        vectorizer = TfidfVectorizer(ngram_range=(2, 4), analyzer='char_wb')
        tfidf = vectorizer.fit_transform([str(student_ans).lower(), str(model_ans).lower()])
        similarity = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        final_score = round(similarity * 100)
        return final_score if final_score >= 40 else 0
    except:
        return 0

def extract_smart_text(file):
    text_data, full_text_raw = [], ""
    if file.name.endswith('.pdf'):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                full_text_raw += page.get_text() + " "
                for b in page.get_text("dict")["blocks"]:
                    if "lines" in b:
                        for l in b["lines"]:
                            for s in l["spans"]:
                                is_bold = "bold" in s["font"].lower() or s["size"] > 12
                                if s["text"].strip():
                                    text_data.append({"text": s["text"].strip(), "is_heading": is_bold})
    else:
        doc = Document(file)
        for p in doc.paragraphs:
            full_text_raw += p.text + " "
            text_data.append({"text": p.text.strip(), "is_heading": any(run.bold for run in p.runs)})
    return text_data, full_text_raw

def generate_smart_exam(data, full_text, difficulty, default_time):
    extracted = []
    if difficulty == "سهل":
        min_len, max_len = 30, 100
    elif difficulty == "متوسط":
        min_len, max_len = 101, 250
    else:
        min_len, max_len = 251, 600

    sentences = [s.strip() for s in re.split(r'[.\n]', full_text) if min_len < len(s.strip()) < max_len]
    logic_keys = ["هو", "هي", "يعتبر", "تعتبر", "يتكون", "يتميز", "يهدف"]

    for s in sentences:
        found_key = next((k for k in logic_keys if f" {k} " in s), None)
        if found_key or ":" in s:
            parts = s.split(":", 1) if ":" in s else s.split(found_key, 1)
            subj, content = parts[0].strip(), parts[1].strip()
            q_type = random.choice(["صح_خطأ", "اختياري", "مقالي"])

            if q_type == "صح_خطأ":
                extracted.append({"q": f"هل صحيح أن {subj} {found_key if found_key else ''} {content}؟", "a": "صح", "type": "صح_خطأ", "time": default_time, "options": ["صح", "خطأ"]})
            elif q_type == "اختياري":
                opts = [content, "خيار بديل 1", "خيار بديل 2"]; random.shuffle(opts)
                extracted.append({"q": f"حدد المفهوم الصحيح لـ ({subj})؟", "a": content, "type": "اختياري", "time": default_time, "options": opts})
            else:
                extracted.append({"q": f"بناءً على المنهج، اشرح بالتفصيل مفهوم: {subj}", "a": content, "type": "مقالي", "time": default_time, "options": []})
    return extracted

# --- 3. إدارة الجلسة (توحيد المتغيرات) ---
if 'qa_pairs' not in st.session_state: st.session_state.qa_pairs = []
if 'exam_active' not in st.session_state: st.session_state.exam_active = False
if 'is_authenticated' not in st.session_state: st.session_state.is_authenticated = False
if 'step' not in st.session_state: st.session_state.step = 'teacher_setup'
if 'st_info' not in st.session_state: st.session_state.st_info = {}
if 'st_ans_list' not in st.session_state: st.session_state.st_ans_list = []
if 'curr' not in st.session_state: st.session_state.curr = 0
if 'q_start' not in st.session_state: st.session_state.q_start = 0
if 'final_score_str' not in st.session_state: st.session_state.final_score_str = ""

# --- 4. الواجهة الرئيسية ---
st.markdown(f"<div style='text-align: center;'><h1 style='color: #1E3A8A;'>🎓 المساعد الذكي | Smart Assistant</h1><h3 style='color: #1E3A8A;'>الجامعة الأسمرية | كلية التربية - قسم الحاسوب</h3></div>", unsafe_allow_html=True)

tab_teacher, tab_student = st.tabs(["👨‍🏫 بوابة المعلم", "👨‍🎓 بوابة الطالب"])

with tab_teacher:
    if not st.session_state.is_authenticated:
        with st.form("teacher_login"):
            pwd = st.text_input("كلمة مرور المسؤول", type="password")
            if st.form_submit_button("دخول"):
                if pwd == "admin":
                    st.session_state.is_authenticated = True; st.rerun()
                else: st.error("❌ كلمة المرور خاطئة")
    else:
        menu = st.radio("القائمة:", ["إعداد الاختبار", "النتائج والتقارير"], horizontal=True)
        if menu == "إعداد الاختبار":
            file = st.file_uploader("ارفع المنهج الدراسي (PDF/DOCX)", type=['pdf', 'docx'])
            col1, col2 = st.columns(2)
            diff = col1.selectbox("مستوى الصعوبة", ["سهل", "متوسط", "عالي"])
            d_time = col2.number_input("الزمن الافتراضي للسؤال (ثواني)", value=120)

            if st.button("✨ توليد الاختبار ذكياً"):
                if file:
                    data, full_text = extract_smart_text(file)
                    st.session_state.qa_pairs = generate_smart_exam(data, full_text, diff, d_time)
                    st.session_state.step = 'teacher_review'; st.rerun()

            if st.session_state.step == 'teacher_review' and st.session_state.qa_pairs:
                for i, q in enumerate(st.session_state.qa_pairs):
                    with st.expander(f"📝 تعديل سؤال {i + 1} ({q['type']})"):
                        c1, c2, c3 = st.columns([2, 2, 1])
                        with c1:
                            new_ty = st.selectbox(f"النمط {i}", ["مقالي", "صح_خطأ", "اختياري"], index=["مقالي", "صح_خطأ", "اختياري"].index(q['type']), key=f"ty_{i}")
                            if new_ty != q['type']:
                                q['type'] = new_ty; q['q'] = reformulate_question(q['q'], new_ty); st.rerun()
                        with c2: q['time'] = st.number_input(f"زمن {i}", value=q['time'], key=f"tm_{i}")
                        with c3:
                            if st.button(f"🗑️ حذف {i+1}", key=f"del_{i}"): st.session_state.qa_pairs.pop(i); st.rerun()
                        q['q'] = st.text_input(f"السؤال {i+1}", q['q'], key=f"qi_{i}")
                        q['a'] = st.text_area(f"الإجابة {i+1}", q['a'], key=f"ai_{i}")

                if st.button("🚀 تفعيل الاختبار للطلاب"):
                    st.session_state.exam_active = True; st.balloons(); st.success("تم التفعيل!")

        elif menu == "النتائج والتقارير":
            if os.path.exists("permanent_results.xlsx"):
                df = pd.read_excel("permanent_results.xlsx")
                st.dataframe(df, use_container_width=True)
                with open("permanent_results.xlsx", "rb") as f:
                    st.download_button("📥 تحميل Excel", f, "results.xlsx")
            else: st.info("لا توجد نتائج بعد.")

with tab_student:
    if not st.session_state.exam_active:
        st.warning("🕒 الاختبار غير متاح حالياً.")
    else:
        if st.session_state.step in ['teacher_review', 'teacher_setup', 'student_login']:
            st.markdown("<div class='question-card'>", unsafe_allow_html=True)
            name = st.text_input("الاسم الثلاثي")
            id_st = st.text_input("رقم القيد")
            if st.button("بدء الاختبار 🏁") and name and id_st:
                st.session_state.update({"st_info": {"name": name, "id": id_st}, "st_ans_list": [], "curr": 0, "q_start": time.time(), "step": 'student_exam'})
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        elif st.session_state.step == 'student_exam':
            idx = st.session_state.curr
            item = st.session_state.qa_pairs[idx]
            rem = max(0, int(item['time'] - (time.time() - st.session_state.q_start)))

            st.markdown(f"<div style='text-align:center; padding:10px; background-color:#fff3cd; border-radius:10px;'>⏳ المتبقي: {rem}ث</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='question-card'><h3>سؤال {idx + 1}</h3><p>{item['q']}</p></div>", unsafe_allow_html=True)

            if item['type'] == "صح_خطأ": ans = st.radio("الإجابة:", ["صح", "خطأ"], key=f"ans_{idx}", index=None)
            elif item['type'] == "اختياري": ans = st.radio("الإجابة:", item['options'], key=f"ans_{idx}", index=None)
            else: ans = st.text_area("إجابتك:", key=f"ans_{idx}")

            if st.button("التالي ⬅️" if idx < len(st.session_state.qa_pairs)-1 else "🚀 تسليم") or rem == 0:
                sc = calculate_smart_score(ans, item['a']) if item['type'] == "مقالي" else (100 if ans == item['a'] else 0)
                st.session_state.st_ans_list.append({"q_text": item['q'], "student_ans": ans, "correct_ans": item['a'], "q_score": sc})
                
                if idx < len(st.session_state.qa_pairs) - 1:
                    st.session_state.curr += 1; st.session_state.q_start = time.time(); st.rerun()
                else:
                    avg = sum([x['q_score'] for x in st.session_state.st_ans_list]) / len(st.session_state.qa_pairs)
                    st.session_state.final_score_str = f"{avg:.1f}%"
                    save_to_permanent_excel(st.session_state.st_info, st.session_state.st_ans_list, st.session_state.final_score_str)
                    st.session_state.step = 'student_result'; st.rerun()
            
            if rem > 0: time.sleep(1); st.rerun()

        elif st.session_state.step == 'student_result':
            st.success(f"✅ تم الانتهاء! درجتك: {st.session_state.final_score_str}")
            if st.button("خروج"): st.session_state.clear(); st.rerun()

with st.sidebar:
    qr = qrcode.make("https://projectpython-djr6lbvhyrrwhbzuhk339w.streamlit.app/")
    img_io = io.BytesIO(); qr.save(img_io, 'PNG')
    st.image(img_io.getvalue(), caption="باركود الدخول")
    if st.button("🚨 تصفير النظام"): st.session_state.clear(); st.rerun()
