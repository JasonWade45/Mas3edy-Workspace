from __future__ import annotations
import uuid
import sys
from pathlib import Path
import streamlit as st

# إضافة مسار المجلد الأساسي للاستيراد
sys.path.append(str(Path(__file__).parent / "core"))

from core.storage import load_config, save_config, save_chat, list_chats, load_chat, delete_chat, audit
from core.secrets_store import set_secret, get_secret, delete_secret
from core.providers import PRESETS, Provider, list_models
from core.assistant_core import run_assistant
from core.filetools import proposal_diff, approve_proposal, list_files

# --- إعدادات الصفحة ---
st.set_page_config(page_title="Mas3edy Workspace", page_icon="✦", layout="wide", initial_sidebar_state="expanded")

# --- التصميم الاحترافي الثابت (بدون أعطال) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;800&display=swap');

/* 1. الخط الأساسي */
html, body, [class*="css"] {
    font-family: 'Tajawal', sans-serif !important;
}

/* 2. الخلفية الداكنة للتطبيق */
.stApp {
    background-color: #0E1117 !important;
    color: #E2E8F0 !important;
}

/* 3. إخفاء القوائم المزعجة */
#MainMenu, footer, header {visibility: hidden;}

/* 4. تنسيق الشريط الجانبي (ثابت على الشمال ونصوصه عربية) */
[data-testid="stSidebar"] {
    background-color: #161B22 !important;
    border-right: 1px solid #30363D !important;
    direction: rtl; /* النص عربي */
}

/* 5. المحتوى الرئيسي (عربي من اليمين للشمال) */
.main .block-container {
    direction: rtl;
    text-align: right;
    padding-top: 2rem;
    padding-right: 2rem;
    max-width: 1200px;
}

/* 6. أزرار الشريط الجانبي */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    border: none;
    background-color: transparent;
    color: #94A3B8;
    justify-content: flex-start;
    padding: 10px 15px;
    border-radius: 8px;
    font-weight: 500;
    transition: all 0.2s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #1E293B;
    color: #F8FAFC;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background-color: #2563EB;
    color: white;
    margin-bottom: 15px;
    justify-content: center;
}

/* 7. كروت الإحصائيات */
.metric-card {
    background-color: #161B22;
    border: 1px solid #30363D;
    border-radius: 12px;
    padding: 24px;
    text-align: center;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    margin-bottom: 20px;
    height: 100%;
}
.metric-value {
    font-size: 2.4rem;
    font-weight: 800;
    color: #3B82F6;
    margin: 10px 0;
}
.metric-label {
    font-size: 1.1rem;
    color: #94A3B8;
    font-weight: 500;
}

/* 8. كارت التنبيه المخصص */
.custom-alert {
    background-color: #1E293B;
    border: 1px solid #334155;
    color: #E2E8F0;
    padding: 24px;
    border-radius: 12px;
    text-align: center;
    font-size: 1.1rem;
    margin-top: 20px;
}

/* 9. حقل الإدخال */
[data-testid="stChatInput"] {
    background-color: #1E293B !important;
    border: 1px solid #334155 !important;
}
[data-testid="stChatInput"] textarea { color: #F8FAFC !important; }
</style>
""", unsafe_allow_html=True)

# --- تهيئة الجلسة ---
if "cfg" not in st.session_state: st.session_state.cfg = load_config()
if "active_tab" not in st.session_state: st.session_state.active_tab = "لوحة التحكم"
if "mode" not in st.session_state: st.session_state.mode = "chat"
if "chat_id" not in st.session_state: st.session_state.chat_id = str(uuid.uuid4())
if "messages" not in st.session_state: st.session_state.messages = []
if "pending" not in st.session_state: st.session_state.pending = []
if "fetched_models" not in st.session_state: st.session_state.fetched_models = []

cfg = st.session_state.cfg

# --- الشريط الجانبي ---
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #3B82F6; font-weight: 800;'>✦ مساعدي</h2>", unsafe_allow_html=True)
    
    if st.button("＋ محادثة جديدة", use_container_width=True, type="primary"):
        st.session_state.chat_id, st.session_state.messages, st.session_state.pending = str(uuid.uuid4()), [], []
        st.session_state.active_tab = "المحادثة"
        st.rerun()
        
    st.markdown("<hr style='border-color: #30363D;'>", unsafe_allow_html=True)
    
    tabs = [
        "لوحة التحكم", "المحادثة", "الوكلاء (Agents)", "المشاريع", "المهام", "إدارة الملفات",
        "المستندات", "بيئة البرمجة", "البحث في الويب", "قاعدة المعرفة", "الذاكرة", 
        "سير العمل", "سجل النشاط", "التحليلات", "الموديلات", "الإعدادات", "الأمان"
    ]
    
    for tab in tabs:
        if st.button(tab, use_container_width=True, key=f"nav_{tab}"):
            st.session_state.active_tab = tab
            if tab == "المحادثة": st.session_state.mode = "chat"
            elif tab == "بيئة البرمجة": st.session_state.mode = "code"
            st.rerun()

# --- الراوتر ---
tab = st.session_state.active_tab

# 1. لوحة التحكم
if tab == "لوحة التحكم":
    st.title("لوحة التحكم")
    st.markdown("<p style='color: #94A3B8; font-size: 1.1em; margin-bottom: 2rem;'>مرحباً بك في بيئة العمل الخاصة بك.</p>", unsafe_allow_html=True)
    
    # جلب البيانات الحقيقية
    total_chats = len(list_chats("chat"))
    active_providers = len(cfg.get("providers", []))
    approved_folders = len(cfg.get("granted_roots", []))
    
    # تصميم الإحصائيات (كروت)
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">إجمالي المحادثات</div>
            <div class="metric-value">{total_chats}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">المزودون النشطون</div>
            <div class="metric-value">{active_providers}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">المجلدات المصرح بها</div>
            <div class="metric-value">{approved_folders}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">المهام المعلقة</div>
            <div class="metric-value" style="color: #F59E0B; font-size: 1.8rem; margin-top: 15px;">قريباً</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<hr style='border-color: #30363D; margin: 30px 0;'>", unsafe_allow_html=True)
    
    st.subheader("النشاط الأخير")
    st.markdown("""
    <div class="custom-alert">
        سيظهر سجل نشاطك هنا بمجرد أن تبدأ في استخدام مساحة العمل (قراءة ملفات، إجراء محادثات، إلخ).
    </div>
    """, unsafe_allow_html=True)

# 2. المحادثة (Chat)
elif tab == "المحادثة" or tab == "بيئة البرمجة":
    with st.expander("⚙️ إعدادات الجلسة", expanded=False):
        providers = cfg.get("providers", [])
        if providers:
            provider_names = [p["name"] for p in providers]
            active = cfg.get("active_provider") if cfg.get("active_provider") in provider_names else provider_names[0]
            selected = st.selectbox("المزود", provider_names, index=provider_names.index(active))
            p_cfg = next(p for p in providers if p["name"] == selected)
            model_override = st.text_input("Model ID", value=p_cfg["model"])
            
            root = None
            if st.session_state.mode == "code":
                roots = cfg.get("granted_roots", [])
                if roots: root = st.selectbox("مجلد العمل", roots)
                else: st.info("أضف مجلد عمل من الإعدادات.")
        else:
            st.warning("الرجاء إضافة مزود من صفحة الإعدادات أولاً.")
            st.stop()

    system_prompt = "أنت مساعد شخصي عملي وخبير. أجب بالمصرية. كن موجزاً ومفيداً."
    
    if not st.session_state.messages:
        st.markdown("<div style='text-align: center; margin-top: 10vh; color: #64748B;'><h1>✦ كيف يمكنني مساعدتك اليوم؟</h1></div>", unsafe_allow_html=True)
        
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            
    prompt = st.chat_input("اكتب رسالتك هنا...")
    if prompt:
        st.session_state.messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        try:
            api_key = get_secret("provider_"+selected)
            provider = Provider(selected, p_cfg["base_url"], api_key or "", model_override.strip())
            with st.chat_message("assistant"):
                with st.spinner("جاري التفكير..."):
                    answer, proposals, log = run_assistant(provider, st.session_state.messages, system_prompt, root)
                st.markdown(answer)
                    
            st.session_state.pending.extend(proposals)
            st.session_state.messages.append({"role":"assistant","content":answer})
            save_chat(st.session_state.chat_id, st.session_state.mode, st.session_state.messages)
            st.rerun()
        except Exception as exc:
            st.error(f"حدث خطأ: {exc}")

# 3. إدارة الملفات
elif tab == "إدارة الملفات":
    st.title("إدارة الملفات")
    roots = cfg.get("granted_roots", [])
    if not roots:
        st.warning("لا توجد مجلدات مصرح بها. اذهب إلى الإعدادات -> الأمان.")
    else:
        selected_root = st.selectbox("اختر مجلد العمل", roots)
        if st.button("تحديث الملفات"):
            files = list_files(selected_root)
            st.dataframe({"الملفات": files}, use_container_width=True)

# 4. الإعدادات
elif tab == "الإعدادات":
    st.title("الإعدادات")
    
    st.subheader("مزودو الذكاء الاصطناعي")
    with st.expander("➕ إضافة مزود جديد", expanded=True):
        name = st.text_input("اسم المزود", key="cfg_name")
        preset = st.selectbox("النوع", list(PRESETS), key="cfg_preset")
        base = st.text_input("Base URL", value=PRESETS[preset], key="cfg_base")
        key = st.text_input("API Key", type="password", key="cfg_key")
        
        if st.button("جلب الموديلات"):
            if base and key:
                try:
                    with st.spinner("جاري الجلب..."):
                        temp = Provider(name, base, key, "temp")
                        st.session_state.fetched_models = list_models(temp)
                except Exception as e: st.error(str(e))
                
        if st.session_state.fetched_models:
            model = st.selectbox("Model ID", st.session_state.fetched_models)
        else:
            model = st.text_input("Model ID يدوياً")
            
        if st.button("حفظ المزود", type="primary"):
            if name and base and model:
                cfg.setdefault("providers", [])
                cfg["providers"] = [p for p in cfg["providers"] if p["name"] != name]
                cfg["providers"].append({"name":name,"base_url":base,"model":model})
                if key: set_secret("provider_"+name, key)
                cfg["active_provider"] = name
                save_config(cfg)
                st.success("تم الحفظ بنجاح!")
                st.rerun()

    st.subheader("الأمان وصلاحيات المجلدات")
    root_text = st.text_input("مسار مجلد جديد", placeholder=r"C:\Projects")
    if st.button("منح الصلاحية للمجلد"):
        p = Path(root_text).expanduser()
        if p.is_dir():
            cfg.setdefault("granted_roots", [])
            if str(p.resolve()) not in cfg["granted_roots"]:
                cfg["granted_roots"].append(str(p.resolve()))
                save_config(cfg)
                st.rerun()

# 5. أقسام قيد التطوير (Placeholders)
else:
    st.title(tab)
    st.markdown(f"""
    <div style="background-color: #161B22; border: 1px solid #30363D; border-radius: 12px; text-align: center; padding: 50px; margin-top: 20px;">
        <h3 style="color: #3B82F6;">🚀 قيد التطوير (Phase 2)</h3>
        <p style="color: #94A3B8; font-size: 1.1em;">
            قسم <strong>{tab}</strong> سيتم بناؤه في المرحلة القادمة.<br>
            فريق الهندسة يعمل حالياً على الجداول وقواعد البيانات الخاصة بهذا القسم.
        </p>
    </div>
    """, unsafe_allow_html=True)