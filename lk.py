import streamlit as st
from pathlib import Path
from db import list_files, add_declaration, add_file, list_files, update_user, get_user_profile, upsert_user_profile, get_user_by_id
from pdf2image import convert_from_path
import base64
import re
import json
import mimetypes
from datetime import datetime
from typing import Optional
import fitz  
import pandas as pd
import os
from openai import OpenAI

def _norm(s: str) -> str: # Обработка ответа GPT
    s = (s or "").strip().strip('«»"“”')
    s = re.sub(r"\s+", " ", s)
    return s.lower()

def extract_text_from_pdf(pdf_path: str, max_chars: int = 15000) -> str: # Извлечение текста из pdf (если возможно)
    if fitz is None:
        return ""
    try:
        doc = fitz.open(pdf_path)
        parts = []
        for page in doc:
            t = page.get_text("text")
            if t:
                parts.append(t)
        doc.close()
        text = "\n".join(parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... [TRUNCATED]"
        return text
    except Exception:
        return ""

def stream_chat_json(client, model, content, temperature=0.0, max_tokens=4000, placeholder=None): # Стрим ответа LM Studio
    raw = ""
    with client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    ) as r:
        for ev in r:
            if ev.choices and ev.choices[0].delta and ev.choices[0].delta.content:
                chunk = ev.choices[0].delta.content
                raw += chunk
                if placeholder is not None:
                    placeholder.code(raw, language="json")
    return raw

def parse_model_json(raw_text: str) -> dict: # Обработка ответа LM Studio
    if not raw_text:
        return {}
    t = raw_text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)

    s, e = t.find("{"), t.rfind("}")
    if s != -1 and e != -1 and e > s:
        t = t[s:e+1]

    t = re.sub(r'(?<=[:\s])None(?=[,\}\]\s])', 'null', t)
    t = re.sub(r'(?<=[:\s])True(?=[,\}\]\s])', 'true', t)
    t = re.sub(r'(?<=[:\s])False(?=[,\}\]\s])', 'false', t)

    t = re.sub(r',(\s*[}\]])', r'\1', t)
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        t2 = re.sub(r'(?<!\\)\'', '"', t)
        try:
            return json.loads(t2)
        except Exception:
            return {}

def encode_image_to_base64(img_path): # Кодирование изображения
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def make_lm_client():
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)
    return OpenAI(
        base_url="http://localhost:1234/v1",
        api_key="lm-studio"
    )


LM_MODEL = "google/gemma-3-12b"  # Модель LM Studio

################## Страница Личного кабинета ##################
st.set_page_config(page_title="ВЭД-Декларант 2.0", page_icon="🛃", layout="wide")
user = st.session_state.user
st.title(f"Личный кабинет")

tab1, tab2, tab3 = st.tabs([
    "Персональная информация",
    "Создать новую таможенную декларацию",
    "История"
])

################## Информация о пользователе ##################
with tab1:
    user = st.session_state.user
    row = get_user_by_id(user["id"]) or {}

    colL, colR = st.columns([1, 2], vertical_alignment="top")
    avatar_file = None
    with colL:
        st.caption("Фото профиля")
        if row.get("avatar_path") and Path(row["avatar_path"]).exists():
            st.image(row["avatar_path"], width=480)
        else:
            avatar_file = st.file_uploader("Загрузить новое фото", type=["jpg","jpeg","png"], key="avatar_upl")

    with colR:
        with st.form("profile_form", clear_on_submit=False):
            name = st.text_input("Имя", value=row.get("name", user.get("name","")))
            surname  = st.text_input("Фамилия", value=row.get("surname", user.get("surname","")))
            position   = st.text_input("Должность / Роль", value=row.get("position", ""))
            phone      = st.text_input("Телефон", value=row.get("phone", ""))
            email      = st.text_input("Email", value=row.get("email", user.get("email","")))
            company    = st.text_input("Организация", value=row.get("company", ""))
            address    = st.text_area("Адрес", value=row.get("address", ""))
            notes      = st.text_area("Доп. информация", value=row.get("notes", ""))
            save = st.form_submit_button("💾 Сохранить")

        if save:
            avatar_path = row.get("avatar_path")
            if avatar_file is not None:
                ext = Path(avatar_file.name).suffix.lower() or ".png"
                user_dir = Path("profiles") / str(user["id"])
                user_dir.mkdir(parents=True, exist_ok=True)
                avatar_path = str(user_dir / f"avatar{ext}")
                with open(avatar_path, "wb") as f:
                    f.write(avatar_file.read())

            update_user(
                user["id"],
                name=name.strip(),
                surname=surname.strip(),
                position=(position or "").strip(),
                phone=(phone or "").strip(),
                email=(email or "").strip(),
                company=(company or "").strip(),
                address=(address or "").strip(),
                notes=(notes or "").strip(),
                avatar_path=avatar_path,
            )
            st.success("Профиль сохранён ✅")
            st.rerun()

################## Создание декларации ##################
with tab2:
    script_dir = Path(__file__).parent
    upload_dir = script_dir / "uploaded"
    upload_dir.mkdir(exist_ok=True)
    upload_dir_user = upload_dir / str(user["id"])
    upload_dir_user.mkdir(parents=True, exist_ok=True)
    upload_dir_user_images = upload_dir_user / "images"
    upload_dir_user_images.mkdir(parents=True, exist_ok=True)

    st.subheader("Загрузите новый инвойс")
    files = st.file_uploader("Выберите PDF-файлы:", type=["pdf"], accept_multiple_files=True)

################## Обработка загруженного pdf ##################
    if files and st.button("Начать обработку"):
        results = []
        for f in files:
            pdf_path = upload_dir_user_images / f.name
            with open(pdf_path, "wb") as out:
                out.write(f.read())
            add_file(user["id"], f.name, f.type, pdf_path.stat().st_size, str(pdf_path))
            embedded_text = extract_text_from_pdf(str(pdf_path), max_chars=15000)
            
            output_dir = pdf_path.parent
            pages = convert_from_path(str(pdf_path), dpi=1200)
            image_paths = []
            for i, page in enumerate(pages, start=1):
                image_path = output_dir / f"{pdf_path.stem}_page_{i}.jpg"
                page.save(image_path, "JPEG")
                image_paths.append(str(image_path))
            
            fixed_prompt = """
            Ты — эксперт по внешнеэкономической деятельности и классификации товаров по ТН ВЭД ЕАЭС.

            Твоя задача:
            1. Извлеки текст со всех предоставленных изображений.
            2. Преобразуй данные в структурированный словарь строго по указанному ниже шаблону.
            3. Все значения должны быть в строковом формате, кроме списков.
            4. Для поля "Номер документа" используй значение для "Invoice No."
            5. Не добавляй лишних полей. Если данные отсутствуют или ты не смог корректно определить его для указанного поля пиши null.

            Пример словаря:
            {
                "Общая информация": {"Номер документа": "1234567890",
                                    "Дата документа": "01.01.2001",
                                "Срок оплаты": "10 дней"},
                "Поставщик": {"Название компании": "ООО 'Компания'",
                            "Юридический адрес": "Невский пр-кт, дом 1, Санкт-Петербург, Россия"
                            "Страна": "Россия",
                            "ИНН": "1234567890",
                            "КПП": "1234567890",
                            "Контакты": {"Контактное лицо": "Иван Иванов",
                                        "Телефон": "88005553535",
                                        "Почта": "123@mail.ru"},
                            "Погрузка": {"Место погрузки": "Невский пр-кт, дом 1, Санкт-Петербург, Россия",
                                        "Дата погрузки": "01.01.2001"}
                "Покупатель": {"Название компании": "ООО 'Компания'",
                            "Юридический адрес": "Невский пр-кт, дом 1, Санкт-Петербург, Россия"
                            "Страна": "Россия"
                            "ИНН": "1234567890",
                            "КПП": "1234567890",
                            "Контакты": {"Контактное лицо": "Иван Иванов",
                                        "Телефон": "88005553535",
                                        "Почта": "123@mail.ru"},
                            "Разгрузка": {"Место разгрузки": "Невский пр-кт, дом 1, Санкт-Петербург, Россия",
                                        "Дата разгрузки": "01.01.2001"}
                "Товары": [
            `			   {"Наименование": "Товар1",
                        "Количество": "1",
                        "Цена": "1",
                        "Валюта": "RUB",
                        "Стоимость": "1",
                        "Страна-производитель": "Страна1",
                        "Код ТНВЭД": "1111111111",
                        "Дополнительная информация": <информация, не вошедшая в предыдущие ключи>},

                        {"Наименование": "Товар2",
                        "Количество": "2",
                        "Цена": "2",
                        "Валюта": "RUB",
                        "Стоимость": "2",
                        "Страна-производитель": "Страна1",
                        "Код ТНВЭД": "2222222222"
                        "Дополнительная информация": <информация, не вошедшая в предыдущие ключи>}
                        ]			 
            }
            """
            client = make_lm_client()
            content_parts = [{"type": "text", "text": fixed_prompt}]
            if embedded_text.strip():
                content_parts.append({
                    "type": "text",
                    "text": "Встроенный текст PDF (без OCR). Используй как первичный источник:\n\n" + embedded_text
                })
            for img_path in image_paths:
                img_b64 = encode_image_to_base64(img_path)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}"
                    }
                })
            live = st.empty()
            raw = stream_chat_json(
                client, LM_MODEL, content_parts,
                temperature=0.0, max_tokens=2048, placeholder=live
            )
            data_to_save = parse_model_json(raw)


            ################## Определение кода ТНВЭД (API GPT) ##################
            product_names = []
            if isinstance(data_to_save, dict):
                items = data_to_save.get("Товары", [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            name = item.get("Наименование", "")
                            extra = item.get("Дополнительная информация", "")
                            # Склеиваем, если есть доп. инфа
                            full_name = name.strip()
                            if extra and extra.lower() != "null":
                                full_name += f" ({extra.strip()})"
                            if full_name:
                                product_names.append(full_name)

            gpt_input = {"Товары": [{"Наименование": name} for name in product_names]}
            gpt_client = make_gpt_client()
            gpt_response = gpt_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Ты — эксперт по классификации товаров по ТН ВЭД ЕАЭС."},
                    {"role": "user", "content": f"Определи 10-значные коды ТН ВЭД для следующих товаров:\n{json.dumps(gpt_input, ensure_ascii=False)}\n Верни в формате: \n <Наименование товара из входных данных> ; <Код ТНВЭД>"}
                ]
            )

            gpt_output = gpt_response.choices[0].message.content
            st.write("Предполагаемые коды ТН ВЭД:\n", gpt_output)

            ################## Добавление кода ТНВЭД в JSON ##################
            code_by_index = {}
            code_by_name = {}
            for raw_line in gpt_output.strip().splitlines():
                if ";" not in raw_line:
                    continue
                left, right = [p.strip() for p in raw_line.split(";", 1)]
                code = right 

                m = re.search(r"товар\s*(\d+)", left, flags=re.I)
                if m:
                    idx = int(m.group(1)) - 1
                    if idx >= 0:
                        code_by_index[idx] = code
                else:
                    code_by_name[_norm(left)] = code

            for idx, item in enumerate(data_to_save.get("Товары", [])):
                if idx in code_by_index:
                    item["Код ТНВЭД"] = code_by_index[idx]
                    continue

                name = (item.get("Наименование") or "").strip()
                extra = (item.get("Дополнительная информация") or "").strip()

                candidates = [_norm(name)]
                if extra and extra.lower() != "null":
                    candidates.append(_norm(f"{name} ({extra})"))

                matched = False
                for cand in candidates:
                    if cand in code_by_name:
                        item["Код ТНВЭД"] = code_by_name[cand]
                        matched = True
                        break
                if matched:
                    continue

                for cand in candidates:
                    for k, v in code_by_name.items():
                        if cand and (k in cand or cand in k):
                            item["Код ТНВЭД"] = v
                            matched = True
                            break
                    if matched:
                        break

            ################## Выгрузка json файла ##################
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = pdf_path.parent / f"{pdf_path.stem}_result_{ts}.json"
            json_bytes = json.dumps(data_to_save, ensure_ascii=False, indent=2).encode("utf-8")
            with open(json_path, "wb") as f:
                f.write(json_bytes)

            add_file(
                user["id"],
                json_path.name,
                "application/json",
                len(json_bytes),
                str(json_path)
            )

            st.download_button(
                label="⬇️ Скачать JSON",
                data=json_bytes,
                file_name=json_path.name,
                mime="application/json",
                key=f"download_{json_path.name}",
            )
            
################## История файлов ##################
with tab3:
    rows = list_files(user["id"]) 
    if not rows:
        st.info("Файлов пока нет.")
    else:
        table = []
        for r in rows:
            table.append({
                "id": r["id"],
                "Имя файла": r["filename"],
                "Тип": (r.get("mime") or "").split("/")[-1] or "file",
                "Размер, КБ": round((r.get("size_bytes") or 0) / 1024, 1),
                "Дата/время загрузки": r.get("created_at") or "",
                "Путь": r.get("stored_path") or "",
            })

        st.dataframe(
            [{k: v for k, v in row.items() if k != "Путь"} for row in table],
            use_container_width=True,
            hide_index=True,
        )
        names = [row["Имя файла"] for row in table]
        sel_name = st.selectbox("Выберите файл", names, index=0)
        chosen = next(t for t in table if t["Имя файла"] == sel_name)
        file_path = Path(chosen["Путь"])
        mime = next((r["mime"] for r in rows if r["filename"] == sel_name), "application/octet-stream")

        col1, col2 = st.columns(2)
        with col1:
            if file_path.exists():
                data = file_path.read_bytes()
                st.download_button(
                    "⬇️ Скачать выбранный файл",
                    data=data,
                    file_name=file_path.name,
                    mime=mime or "application/octet-stream",
                    use_container_width=True,
                )
            else:
                st.error("Файл на диске не найден.")

        ################## Предпросмотр файла ##################
        with col2:
            if mime == "application/pdf":
                thumb = None
                candidate = file_path.parent / f"{file_path.stem}_page_1.jpg"
                if candidate.exists():
                    thumb = candidate
                if thumb:
                    st.image(str(thumb), caption="Стр. 1 (превью)", use_container_width=True)
                else:
                    st.caption("Предпросмотр: изображение первой страницы не найдено.")
            elif (mime or "").startswith("image/"):
                st.image(str(file_path), use_container_width=True)
            elif (mime or "") == "application/json":
                try:
                    st.json(json.loads(file_path.read_text(encoding="utf-8")))
                except Exception:
                    st.code(file_path.read_text(encoding="utf-8")[:5000])