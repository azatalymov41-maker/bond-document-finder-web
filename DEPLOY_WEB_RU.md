# Публикация Bond Document Finder как веб-сайта

**Это веб-проект на Streamlit, а не EXE.** Для первого запуска не нужен платный сервер: можно использовать Streamlit Community Cloud. Для пользователей сайт будет открываться по ссылке вида `https://<app-name>.streamlit.app`.

## 1. Создайте репозиторий GitHub

1. Зарегистрируйтесь / войдите на https://github.com/ .
2. Нажмите **New repository**; имя, например, `bond-document-finder-web`.
3. Распакуйте ZIP. Загрузите в **корень** репозитория содержимое папки `bond-document-finder-web` (важно, чтобы `app.py` и `requirements.txt` лежали в корне).
4. **Никогда не загружайте** `.env`, `.streamlit/secrets.toml`, пароли или API-ключи. Файлы `.env.example` и `secrets.toml.example` — безопасные шаблоны.

Если предпочитаете Git, команды после создания пустого GitHub-репозитория:

```powershell
cd C:\path\to\bond-document-finder-web
git init
git add .
git commit -m "Initial web SEC document finder"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/bond-document-finder-web.git
git push -u origin main
```

## 2. Опубликуйте Streamlit-приложение

1. Откройте https://share.streamlit.io/ и войдите через GitHub.
2. Создайте приложение (**Create app / Deploy an app from GitHub**).
3. Выберите репозиторий, ветку `main`, **Main file path: `app.py`**.
4. В дополнительных настройках (**Advanced settings → Secrets**) добавьте:

```toml
SEC_USER_AGENT = "YourCompany BondDocumentFinder name@real-contact-domain.com"
SEC_MIN_INTERVAL = "0.7"
SEC_TIMEOUT = "18"
```

5. Замените вымышленные данные в `SEC_USER_AGENT` на **настоящие данные владельца приложения** (имя/организация и действительный контактный email). Важна идентификация запросов к SEC согласно Fair Access. Не добавляйте секреты в GitHub.
6. Нажмите **Deploy**. После успешного развёртывания Streamlit выдаст URL вашего приложения.

## 3. Тестирование опубликованного сайта

Начните с:

- `US03772CAA18` — APLD ComputeCo 2; в дополнительных параметрах укажите CIK материнской компании `1144879`, coupon `6.75`, maturity `2031-03-15`.
- `US595112AN31` — Micron Technology 2.375% 2032; CIK `723125`.
- `Prologis Euro Finance 4% 05.05.2034 EUR` — натуральный текст без ISIN.

Посмотрите «Ошибки и ограничения» и журнал. Если появляется **403 / 429**, SEC ограничил доступ: это *не означает*, что документа нет. Cloud IP иногда блокируются SEC. Если на вашем хостинге SEC недоступен, приложение можно перенести на VPS/Render/другой хостинг, с соблюдением правил SEC.

## 4. Как запустить веб-сайт на своём Windows-компьютере

```powershell
cd C:\path\to\bond-document-finder-web
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

В `.env` укажите реальный `SEC_USER_AGENT`. Затем откройте `http://localhost:8501`.

## 5. Ограничения текущей версии

- **SEC-only**: без LuxSE, LSE, CNMV, прямого поиска на сайтах эмитентов и платных баз.
- Используется SEC Full Text Search — веб-интерфейс с JSON endpoint, который не гарантируется SEC как стабильный документированный API. Используется также официальный Submissions API.
- Вывод «Primary document candidate — review» требует ручного подтверждения; **это не финальная юридическая верификация**.
- В частных Rule 144A может не быть публичного Offering Memorandum.
- На Streamlit Community Cloud возможны таймауты или 403 от SEC; использование другого хостинга не гарантирует решение.
- Глубокая история не всех filings автоматически загружается; для старых размещений эффективнее вводить CIK и искать по ISIN/купону.
- Приложение пока не подключает OpenAI API и не имеет пользовательской авторизации.
- Для конфиденциальных запросов не публикуйте приватные данные в открытом приложении.

## 6. Дальнейшая разработка в Codex

Передайте Codex этот проект и попросите сначала провести реальные live-тесты SEC в среде с разрешённым доступом, затем добавить Index-aware search всех исторических filings, issuer / parent company graph, международные площадки и более строгую верификацию документов.
