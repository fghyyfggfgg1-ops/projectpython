import streamlit as st
import fitz  # PyMuPDF
from docx import Document
import random
import re
import qrcode
import pandas as pd
import io
import time

# المكتبات للتقييم الدلالي
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# --- 1. إعدادات الصفحة ---
st.set_page_config(page_title="Edu-AI | نظام الجامعة الأسمرية", page_icon="🎓", layout="wide")

# --- 2. كود CSS (تنسيق الواجهة) ---
st.markdown("""
    <style>
    html, body, [data-testid="stAppViewContainer"], .main, [data-testid="stHeader"] {
        direction: rtl !important; text-align: right !important;
    }
    [data-testid="stSidebar"] { direction: rtl !important; text-align: right !important; }
    h1, h2, h3, h4, h5, h6, p, span, label, .stMarkdown div {
        direction: rtl !important; text-align: right !important; display: block !important;
    }
    .rtl-header {
        display: block; width: 100%; text-align: right !important; direction: rtl !important;
        font-size: 22px; font-weight: bold; color: #1E3A8A; padding: 10px 0;
        border-right: 8px solid #1E3A8A; padding-right: 15px; margin-bottom: 20px;
    }
    .q-timer-box {
        position: fixed; top: 80px; left: 20px; background: #E11D48; color: white;
        padding: 10px 20px; border-radius: 12px; z-index: 1000; font-weight: bold;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2); font-size: 18px; border: 2px solid white;
    }
    .q-container { background-color: #f0f7ff; border-right: 10px solid #1e3a8a; padding: 20px; border-radius: 10px; margin-bottom: 15px; }
    div.stButton > button { width: auto !important; min-width: 150px; border-radius: 10px; height: 45px; background-color: #1E3A8A !important; color: white !important; }
    .delete-btn button { background-color: #dc2626 !important; min-width: 80px !important; }
    .add-btn button { background-color: #10b981 !important; color: white !important; border: none !important; }
    </style>
    """, unsafe_allow_html=True)


# --- 3. الدوال المساعدة ---
def calculate_smart_score(student_ans, model_ans):
    if not student_ans or len(str(student_ans).strip()) < 2:
        return 0

    s1, s2 = str(student_ans).strip().lower(), str(model_ans).strip().lower()
    if s1 == s2: return 100

    try:
        # العودة لنظام char_wb لكن مع ضبط المعايير بدقة
        vectorizer = TfidfVectorizer(ngram_range=(2, 4), analyzer='char_wb')
        tfidf_matrix = vectorizer.fit_transform([s1, s2])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]

        final_score = round(similarity * 100)

        # عتبة 40% هي الأنسب: تحمي من الإجابات العشوائية وتدعم الإجابات القريبة
        return final_score if final_score >= 40 else 0
    except:
        return 0


def get_file_details(file):
    text = ""
    if file.name.endswith('.pdf'):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc: text += page.get_text() + " "
    else:
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
    return text


if 'step' not in st.session_state: st.session_state.step = 'teacher_upload'


# --- 4. إدارة الجلسة ---
def smart_question_engine(text, difficulty):
    extracted = []

    # 1. تحديد معايير الصعوبة (طول الجملة المستهدفة)
    if difficulty == "سهل":
        min_len, max_len = 30, 100  # جمل بسيطة ومباشرة
        default_time = 60  # زمن مقترح أولي
    elif difficulty == "متوسط":
        min_len, max_len = 101, 250  # جمل متوسطة الطول (شرح)
        default_time = 120  # زمن مقترح أولي
    else:  # عالي / صعب جداً
        min_len, max_len = 251, 600  # فقرات دسمة (تحليل)
        default_time = 300  # زمن مقترح أولي

    # تقسيم النص إلى جمل بناءً على المعايير
    sentences = [s.strip() for s in re.split(r'[.\n]', text) if min_len < len(s.strip()) < max_len]

    logic_keys = ["هو", "هي", "يعتبر", "تعتبر", "يتكون", "يتميز", "يهدف"]

    for s in sentences:
        found_key = next((k for k in logic_keys if f" {k} " in s), None)
        if found_key or ":" in s:
            parts = s.split(":", 1) if ":" in s else s.split(found_key, 1)
            subj, content = parts[0].strip(), parts[1].strip()

            # اختيار نوع السؤال عشوائياً (مع الحفاظ على الأنواع الثلاثة)
            q_type = random.choice(["صح_خطأ", "اختياري", "مقالي"])

            # إنشاء كائن السؤال بالزمن "المقترح"
            if q_type == "صح_خطأ":
                extracted.append({
                    "q": f"هل صحيح أن {subj} {found_key if found_key else ''} {content}؟",
                    "a": "صح",
                    "type": "صح_خطأ",
                    "time": default_time,  # القيمة المقترحة التي تظهر في شاشة المراجعة
                    "options": []
                })
            elif q_type == "اختياري":
                opts = [content, "خيار بديل 1", "خيار بديل 2"]
                random.shuffle(opts)
                extracted.append({
                    "q": f"حدد المفهوم الصحيح لـ ({subj})؟",
                    "a": content,
                    "type": "اختياري",
                    "time": default_time,
                    "options": opts
                })
            else:
                extracted.append({
                    "q": f"بناءً على المنهج، اشرح بالتفصيل مفهوم: {subj}",
                    "a": content,
                    "type": "مقالي",
                    "time": default_time,
                    "options": []
                })

    return extracted


if 'current_q_idx' not in st.session_state: st.session_state.current_q_idx = 0
if 'qa_pairs' not in st.session_state: st.session_state.qa_pairs = []

# --- 5. القائمة الجانبية ---
# --- 5. القائمة الجانبية (Sidebar) بعد الإصلاح ---
with st.sidebar:
    st.markdown("<h2 style='text-align: center;'>📊 بوابة Edu-AI</h2>", unsafe_allow_html=True)

    # تحسين عرض الباركود ليظهر بحجم واضح (حل مشكلة الحجم الصغير)
    st.markdown("##### 📱 كود الدخول للاختبار:")

    # توليد الباركود مباشرة (بدون الحاجة لدالة خارجية)
    qr_url = "https://edu-ai-asmarya.streamlit.app"
    qr = qrcode.make(qr_url)
    buf_qr = io.BytesIO()
    qr.save(buf_qr, format="PNG")

    # استخدام use_container_width لجعل الباركود يملأ عرض القائمة الجانبية
    st.image(buf_qr, caption="امسح الكود للدخول السريع", use_container_width=True)

    st.divider()

    # زر تصفير النظام
    if st.button("🔄 تصفير النظام", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- 6. الواجهة الرئيسية ---
st.markdown("<div style='text-align: center;'><h1 style='color: #1E3A8A;'>🎓 نظام مساعد التقييم الذكي</h1>"
            "<h3 style='color: #1E3A8A;'>الجامعة الأسمرية | كلية التربية - قسم الحاسوب</h3></div>",
            unsafe_allow_html=True)
st.divider()

# المرحلة 1: الرفع + تحديد المستوى (Dropdown كما في الصورة)
if st.session_state.step == 'teacher_upload':
    st.markdown("<div class='rtl-header'>👨‍🏫 خطوة (1): إعداد المادة العلمية وتحديد المستوى</div>",
                unsafe_allow_html=True)
    f = st.file_uploader("ارفع المنهج (PDF/DOCX):", type=['pdf', 'docx'])

    # القائمة المنسدلة المحدثة بناءً على صورتك المرفقة
    level_map = {
        "سهل ": "سهل",
        "متوسط ": "متوسط",
        "عالي ": "صعب"
    }
    selected_label = st.selectbox("🎯 حدد مستوى صعوبة الأسئلة المطلوبة:", options=list(level_map.keys()), index=0)

    if f and st.button("توليد الأسئلة ذكياً ✨"):
        content = get_file_details(f)
        st.session_state.qa_pairs = smart_question_engine(content, level_map[selected_label])
        st.session_state.step = 'teacher_review'
        st.rerun()

# المرحلة 2: مراجعة المعلم + زر إضافة سؤال جديد
elif st.session_state.step == 'teacher_review':
    st.markdown("<div class='rtl-header'>📝 خطوة (2): مراجعة وإدارة الأسئلة</div>", unsafe_allow_html=True)

    for i, item in enumerate(st.session_state.qa_pairs):
        with st.expander(f"سؤال {i + 1} | النوع: {item['type']}"):
            col_text, col_act = st.columns([5, 1])
            with col_act:
                if st.button("❌ حذف", key=f"del_{i}"):
                    st.session_state.qa_pairs.pop(i)
                    st.rerun()
            with col_text:
                # خيار تغيير النوع
                st.session_state.qa_pairs[i]['type'] = st.selectbox("نوع السؤال:", ["صح_خطأ", "اختياري", "مقالي"],
                                                                    index=["صح_خطأ", "اختياري", "مقالي"].index(
                                                                        item['type']), key=f"type_{i}")
                st.session_state.qa_pairs[i]['q'] = st.text_input("نص السؤال:", value=item['q'], key=f"q_edit_{i}")

                # التحكم بالزمن يدوياً لكل سؤال
                st.session_state.qa_pairs[i]['time'] = st.number_input("الزمن (ثانية):", value=item['time'],
                                                                       key=f"t_edit_{i}")

                if st.session_state.qa_pairs[i]['type'] == "صح_خطأ":
                    st.session_state.qa_pairs[i]['a'] = st.selectbox("الإجابة:", ["صح", "خطأ"],
                                                                     index=0 if item['a'] == "صح" else 1,
                                                                     key=f"a_edit_{i}")
                elif st.session_state.qa_pairs[i]['type'] == "اختياري":
                    st.session_state.qa_pairs[i]['a'] = st.text_input("الإجابة الصحيحة:", value=item['a'],
                                                                      key=f"a_edit_{i}")
                    opts_str = st.text_area("الخيارات (افصل بينها بفاصلة ,):", value=",".join(item['options']),
                                            key=f"opts_{i}")
                    st.session_state.qa_pairs[i]['options'] = [o.strip() for o in opts_str.split(",") if o.strip()]
                else:
                    st.session_state.qa_pairs[i]['a'] = st.text_area("الإجابة النموذجية:", value=item['a'],
                                                                     key=f"a_edit_{i}")

    st.divider()
    c_add, c_save = st.columns(2)
    with c_add:
        # زر إضافة سؤال يدوي (باللون الأخضر)
        st.markdown('<div class="add-btn">', unsafe_allow_html=True)
        if st.button("➕ إضافة سؤال جديد"):
            st.session_state.qa_pairs.append(
                {"q": "اكتب السؤال هنا", "a": "اكتب الإجابة هنا", "type": "مقالي", "time": 120, "options": []})
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with c_save:
        if st.button("✅ اعتماد الاختبار"):
            st.session_state.step = 'student_login'
            st.rerun()

# باقي المراحل (تسجيل الطالب، أداء الاختبار، التصدير) تستمر بنفس المنطق المستقر
elif st.session_state.step == 'student_login':
    st.markdown("<div class='rtl-header'>👤 خطوة (3): تسجيل دخول الطالب</div>", unsafe_allow_html=True)
    n = st.text_input("الاسم الرباعي:")
    s = st.text_input("رقم القيد:")
    if st.button("بدء الاختبار 🏁") and n and s:
        st.session_state.student_info = {"name": n, "id": s}
        st.session_state.student_answers = [""] * len(st.session_state.qa_pairs)
        st.session_state.q_start_time = time.time()
        st.session_state.step = 'student_exam'
        st.rerun()
#
#
# --- المرحلة 4: أداء الاختبار (حل مشكلة التنسيق والخيارات) ---
elif st.session_state.step == 'student_exam':
    idx = st.session_state.current_q_idx
    item = st.session_state.qa_pairs[idx]
    elapsed = time.time() - st.session_state.q_start_time
    rem = max(0, int(item['time'] - elapsed))

    # حاوية التوقيت
    st.markdown(f"<div class='q-timer-box'>⏳ المتبقي: {rem}ث</div>", unsafe_allow_html=True)

    # حاوية السؤال مع محاذاة لليمين
    st.markdown(f"""
        <div class='q-container' style='text-align: right; direction: rtl;'>
            <h3 style='margin:0;'>سؤال {idx + 1}</h3>
            <p style='font-size: 1.2rem;'>{item['q']}</p>
        </div>
    """, unsafe_allow_html=True)

    # عرض الخيارات بناءً على النوع مع ضمان المحاذاة
    with st.container():
        st.write("---")  # فاصل بصري
        if item['type'] == "صح_خطأ":
            ans = st.radio("اختر الإجابة:", ["صح", "خطأ"], key=f"ans_{idx}", index=None)
        elif item['type'] == "اختياري":
            if item['options']:
                ans = st.radio("اختر الإجابة الصحيحة:", item['options'], key=f"ans_{idx}", index=None)
            else:
                st.warning("⚠️ لا توجد خيارات متاحة لهذا السؤال، يرجى مراجعة الإعدادات.")
        else:
            ans = st.text_area("اكتب إجابتك الاستفاضية هنا:", key=f"ans_{idx}", placeholder="ابدأ الكتابة هنا...")

        st.session_state.student_answers[idx] = ans

    # أزرار التحكم في أسفل الصفحة
    st.write(" ")
    col_prev, col_next = st.columns([5, 1])  # جعل زر التالي في اليمين (حسب RTL)
    with col_next:
        btn_label = "🚀 تسليم" if idx == len(st.session_state.qa_pairs) - 1 else "التالي ⬅️"
        if st.button(btn_label, use_container_width=True):
            if idx < len(st.session_state.qa_pairs) - 1:
                st.session_state.current_q_idx += 1
                st.session_state.q_start_time = time.time()
                st.rerun()
            else:
                st.session_state.step = 'export'
                st.rerun()

    if rem > 0:
        time.sleep(1)
        st.rerun()
#
# --- المرحلة 5: النتائج وتحميل الملف (حل مشكلة عدم ظهور زر التحميل) ---
elif st.session_state.step == 'export':
    # حل مشكلة ظهور الكود النصي باستخدام markdown صحيح
    st.markdown("<div class='rtl-header'>📊 التقرير النهائي للنتيجة</div>", unsafe_allow_html=True)

    # رسالة النجاح في حاوية منسقة
    st.success("✅ تم الانتهاء من الاختبار بنجاح. شكراً لك!")

    # 1. حساب النتائج
    results, total = [], 0
    for i, item in enumerate(st.session_state.qa_pairs):
        s_ans = st.session_state.student_answers[i]
        # منطق التصحيح: تطابق تام للخيارات أو تقييم ذكي للمقالي
        score = 100 if (item['type'] in ["صح_خطأ", "اختياري"] and s_ans == item['a']) else calculate_smart_score(s_ans,
                                                                                                                 item[
                                                                                                                     'a'])
        total += score
        results.append({
            "رقم السؤال": i + 1,
            "نوع السؤال": item['type'],
            "نص السؤال": item['q'],
            "إجابة الطالب": s_ans,
            "الإجابة النموذجية": item['a'],
            "الدرجة": f"{score}%"
        })

    avg_score = int(total / len(st.session_state.qa_pairs))

    # 2. عرض المعدل للطالب
    st.metric("معدل النجاح الإجمالي", f"{avg_score}%")

    # 3. إنشاء ملف Excel (الجزء المسؤول عن زر التحميل)
    df = pd.DataFrame(results)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='النتائج', startrow=4)
        workbook = writer.book
        worksheet = writer.sheets['النتائج']
        worksheet.right_to_left()  # تنسيق من اليمين لليسار داخل الملف

        # إضافة معلومات الطالب في رأس الملف
        header_format = workbook.add_format({'bold': True, 'font_color': '#1E3A8A', 'font_size': 14})
        worksheet.write('A1', f"الاسم: {st.session_state.student_info['name']}", header_format)
        worksheet.write('A2', f"رقم القيد: {st.session_state.student_info['id']}", header_format)
        worksheet.write('A3', f"المعدل النهائي: {avg_score}%", header_format)
        worksheet.set_column('A:F', 25)

    # 4. عرض زر التحميل بشكل واضح
    st.divider()
    col_dl, col_main = st.columns([1, 1])

    with col_dl:
        st.download_button(
            label="📥 تحميل تقرير إجاباتك (Excel)",
            data=output.getvalue(),
            file_name=f"Result_{st.session_state.student_info['id']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with col_main:
        if st.button("🏠 العودة للرئيسية", use_container_width=True):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()
