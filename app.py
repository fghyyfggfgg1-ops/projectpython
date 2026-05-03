import streamlit as st
import fitz  # PyMuPDF
from docx import Document
import random
import re
import qrcode
import pandas as pd
import io
import time
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- 1. إعدادات الصفحة والمحاذاة ---
st.set_page_config(page_title="المساعد الذكي | Smart Assistant", page_icon="🎓", layout="wide")

st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], .main, [data-testid="stHeader"] {
        direction: rtl !important; text-align: right !important;
    }
    .q-container { background-color: #f0f7ff; border-right: 10px solid #1e3a8a; padding: 20px; border-radius: 10px; margin-bottom: 15px; text-align: right; }
    div.stButton > button { border-radius: 10px; background-color: #1E3A8A !important; color: white !important; width: 100%; height: 45px; }
    .timer-box { background: #E11D48; color: white; padding: 10px 20px; border-radius: 12px; text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 10px; }
    .result-card { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-right: 5px solid #10b981; text-align: right; }
    </style>
    """, unsafe_allow_html=True)


# --- 2. محرك القراءة الذكي ---
def extract_smart_text(file):
    text_data = []
    full_text_raw = ""
    if file.name.endswith('.pdf'):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                full_text_raw += page.get_text() + " "
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" in b:
                        for l in b["lines"]:
                            for s in l["spans"]:
                                is_bold = "bold" in s["font"].lower()
                                text_data.append({"text": s["text"], "is_heading": is_bold})
    else:
        doc = Document(file)
        for p in doc.paragraphs:
            full_text_raw += p.text + " "
            is_bold = any(run.bold for run in p.runs)
            text_data.append({"text": p.text, "is_heading": is_bold})
    return text_data, full_text_raw


def generate_smart_exam(data, full_text, difficulty, default_time):
    qa_pairs = []
    headings = [item['text'] for item in data if item['is_heading'] and len(item['text'].strip()) > 5]
    sentences = [s.strip() for s in re.split(r'[.\n!؟]', full_text) if len(s.strip()) > 30]
    limit = {"سهل": 5, "متوسط": 10, "عالي": 15}.get(difficulty, 10)

    for h in headings[:limit // 2]:
        # محاولة إيجاد إجابة نموذجية من النص بدلاً من النص الثابت (تعديل الصورة 3)
        found_ans = "يرجى مراجعة المنهج للتفاصيل."
        for s in sentences:
            if h[:10].lower() in s.lower():
                found_ans = s
                break
        qa_pairs.append(
            {"q": f"ناقش بالتفصيل المفهوم التالي: {h}", "a": found_ans, "type": "مقالي", "time": default_time,
             "options": []})

    random.shuffle(sentences)
    for s in sentences[:limit // 2]:
        q_type = random.choice(["صح_خطأ", "اختياري"])
        qa_pairs.append({
            "q": f"اختر الإجابة الصحيحة المتعلقة بـ: {s[:30]}..." if q_type == "اختياري" else f"هل العبارة التالية صحيحة: {s}",
            "a": s if q_type == "اختياري" else "صح", "type": q_type, "time": default_time,
            "options": [s, "خيار بديل 1", "خيار بديل 2"] if q_type == "اختياري" else ["صح", "خطأ"]
        })
    return qa_pairs


def calculate_smart_score(student_ans, model_ans):
    if not student_ans or len(str(student_ans).strip()) < 2: return 0
    try:
        vectorizer = TfidfVectorizer(ngram_range=(2, 4), analyzer='char_wb')
        tfidf_matrix = vectorizer.fit_transform([str(student_ans).lower(), str(model_ans).lower()])
        return round(cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0] * 100)
    except:
        return 0


# --- 3. إدارة الجلسة ---
if 'qa_pairs' not in st.session_state: st.session_state.qa_pairs = []
if 'exam_active' not in st.session_state: st.session_state.exam_active = False
if 'student_step' not in st.session_state: st.session_state.student_step = 'login'
if 'all_results' not in st.session_state: st.session_state.all_results = []
if 'is_authenticated' not in st.session_state: st.session_state.is_authenticated = False

# الباركود (موجود كما طلبت سابقاً في Sidebar)
with st.sidebar:
    qr = qrcode.make("https://smart-assistant-edu.streamlit.app")
    img_io = io.BytesIO()
    qr.save(img_io, 'PNG')
    st.image(img_io.getvalue(), caption="باركود الدخول")

# --- 4. الواجهة الرئيسية ---
st.markdown(f"<div style='text-align: center;'><h1 style='color: #1E3A8A;'>🎓 المساعد الذكي | Smart Assistant</h1>"
            f"<h3 style='color: #1E3A8A;'>الجامعة الأسمرية | كلية التربية - قسم الحاسوب</h3></div>",
            unsafe_allow_html=True)

tab_teacher, tab_student = st.tabs(["👨‍🏫 بوابة المعلم", "👨‍🎓 بوابة الطالب"])

with tab_teacher:
    if not st.session_state.is_authenticated:
        with st.form("login"):
            pwd = st.text_input("كلمة مرور المسؤول", type="password")
            if st.form_submit_button("دخول"):
                if pwd == "admin": st.session_state.is_authenticated = True; st.rerun()
    else:
        menu = st.radio("التحكم:", ["إعداد الاختبار", "النتائج"], horizontal=True)
        if menu == "إعداد الاختبار":
            file = st.file_uploader("ارفع الملف التعليمي (PDF/DOCX):", type=['pdf', 'docx'])
            col1, col2 = st.columns(2)
            diff = col1.selectbox("مستوى الصعوبة:", ["سهل", "متوسط", "عالي"])
            def_time = col2.number_input("المؤقت الافتراضي للسؤال (ثواني):", value=120)

            if file and st.button("توليد الاختبار الذكي ✨"):
                data, full_text = extract_smart_text(file)
                st.session_state.qa_pairs = generate_smart_exam(data, full_text, diff, def_time);
                st.rerun()

            if st.session_state.qa_pairs:
                for i, item in enumerate(st.session_state.qa_pairs):
                    # تعديل الصورة 2: إظهار النمط وإضافة خيارات للاختياري
                    with st.expander(f"تعديل سؤال {i + 1} ({item['type']})"):
                        item['q'] = st.text_input(f"السؤال {i + 1}:", item['q'], key=f"q{i}")
                        item['a'] = st.text_area(f"الإجابة النموذجية {i + 1}:", item['a'], key=f"a{i}")
                        item['type'] = st.selectbox("نمط السؤال:", ["مقالي", "صح_خطأ", "اختياري"],
                                                    index=["مقالي", "صح_خطأ", "اختياري"].index(item['type']),
                                                    key=f"ty{i}")
                        if item['type'] == "اختياري":
                            item['options'][0] = st.text_input("الخيار الصحيح:", item['options'][0], key=f"optc{i}")
                            item['options'][1] = st.text_input("خيار بديل 1:", item['options'][1], key=f"opt1{i}")
                            item['options'][2] = st.text_input("خيار بديل 2:", item['options'][2], key=f"opt2{i}")
                        item['time'] = st.number_input("المؤقت:", value=item['time'], key=f"t{i}")
                        if st.button(f"🗑️ حذف {i + 1}", key=f"del{i}"):
                            st.session_state.qa_pairs.pop(i);
                            st.rerun()
                if st.button("🚀 تفعيل الاختبار للطلاب"): st.session_state.exam_active = True; st.success("تم التفعيل!")

        elif menu == "النتائج":
            if st.session_state.all_results:
                # تحويل النتائج لخلايا منفصلة في الإكسل
                flat_data = []
                for res in st.session_state.all_results:
                    row = {"الاسم": res["الاسم"], "رقم القيد": res["رقم القيد"], "الدرجة الكلية": res["الدرجة"]}
                    for j, detail in enumerate(res["تفاصيل"]):
                        row[f"سؤال {j + 1}"] = detail["السؤال"]
                        row[f"إجابة الطالب {j + 1}"] = detail["إجابة الطالب"]
                        row[f"النموذجية {j + 1}"] = detail["الإجابة النموذجية"]
                    flat_data.append(row)
                df = pd.DataFrame(flat_data)
                st.dataframe(df)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                st.download_button("📥 تحميل النتائج", output.getvalue(), "results.xlsx")

with tab_student:
    if not st.session_state.exam_active:
        st.info("🕒 الاختبار غير متاح حالياً.")
    else:
        if st.session_state.student_step == 'login':
            name = st.text_input("الاسم الثلاثي:")
            id_num = st.text_input("رقم القيد:")
            if st.button("بدء الاختبار") and name and id_num:
                st.session_state.student_info = {"name": name, "id": id_num}
                st.session_state.student_answers = [];
                st.session_state.current_idx = 0
                st.session_state.q_start_time = time.time();
                st.session_state.student_step = 'exam';
                st.rerun()
        elif st.session_state.student_step == 'exam':
            idx = st.session_state.current_idx
            item = st.session_state.qa_pairs[idx]
            rem = max(0, int(item['time'] - (time.time() - st.session_state.q_start_time)))
            st.markdown(f"<div class='timer-box'>⏳ المتبقي: {rem}ث</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='q-container'><h3>سؤال {idx + 1}</h3><p>{item['q']}</p></div>",
                        unsafe_allow_html=True)
            if item['type'] == "مقالي":
                ans = st.text_area("إجابتك:", key=f"ans{idx}")
            else:
                ans = st.radio("اختر الإجابة:", item['options'], key=f"ans{idx}", index=None)
            if st.button("التالي") or rem == 0:
                score = calculate_smart_score(ans, item['a']) if item['type'] == "مقالي" else (
                    100 if ans == item['a'] else 0)
                st.session_state.student_answers.append(
                    {"السؤال": item['q'], "إجابة الطالب": ans, "الإجابة النموذجية": item['a'], "الدرجة": score})
                if idx < len(st.session_state.qa_pairs) - 1:
                    st.session_state.current_idx += 1;
                    st.session_state.q_start_time = time.time();
                    st.rerun()
                else:
                    avg = sum([x['الدرجة'] for x in st.session_state.student_answers]) / len(st.session_state.qa_pairs)
                    st.session_state.all_results.append({"الاسم": st.session_state.student_info['name'],
                                                         "رقم القيد": st.session_state.student_info['id'],
                                                         "الدرجة": f"{avg:.1f}%",
                                                         "تفاصيل": st.session_state.student_answers})
                    st.session_state.student_step = 'result';
                    st.rerun()
            if rem > 0: time.sleep(1); st.rerun()
        elif st.session_state.student_step == 'result':
            st.success(f"درجتك: {st.session_state.all_results[-1]['الدرجة']}")
