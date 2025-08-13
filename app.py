import streamlit as st
from db import init_db, get_user_by_email, create_user

st.set_page_config(page_title="ВЭД-Декларант 2.0", page_icon="🛃", layout="wide")
init_db()

if "user" not in st.session_state:
    st.session_state.user = None

st.title("🛃 ВЭД-Декларант 2.0")
st.caption("Войдите или зарегистрируйтесь, чтобы перейти в личный кабинет.")

tab_login, tab_register = st.tabs(["Вход", "Регистрация"])
################## Вход ##################
with tab_login:
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Логин/Email")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")
    if submitted:
        user = get_user_by_email(email)
        if not user:
            st.error("Пользователь не найден")
        else:
            if password == user["password"]:
                st.session_state.user = {"id": user["id"], "email": user["email"], "name": user["name"], "surname": user["surname"]}
                st.switch_page("pages/lk.py")
            else:
                st.error("Неверный пароль")

################## Регистрация ##################
with tab_register:
    with st.form("register_form", clear_on_submit=True):
        name = st.text_input("Имя пользователя")
        surname = st.text_input("Фамилия")
        email_r = st.text_input("Логин/Email")
        password_r = st.text_input("Пароль", type="password")
        password_r2 = st.text_input("Повторите пароль", type="password")
        reg = st.form_submit_button("Зарегистрироваться")

    if reg:
        if not name or not surname or not email_r or not password_r:
            st.error("Заполните все обязательные поля!")
        elif password_r != password_r2:
            st.error("Пароли не совпадают")
        elif get_user_by_email(email_r):
            st.error("Такой email уже зарегистрирован")
        else:
            create_user(name, surname, email_r, password_r)
            st.success("Регистрация успешна")
