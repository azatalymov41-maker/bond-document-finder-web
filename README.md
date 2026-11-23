# Bond Document Finder — SEC Web MVP

Веб-приложение на **Python + Streamlit** для поиска юридической документации облигаций в SEC EDGAR. Поддерживает ввод ISIN / CUSIP / названия выпуска, поиск по параметрам, SEC Full Text Search, поиск CIK/подач компаний, просмотр приложений к filings, оценку кандидатов и Excel-экспорт.

**📌 Для публикации в интернете:** см. [`DEPLOY_WEB_RU.md`](DEPLOY_WEB_RU.md).

## Быстрый запуск на Windows

1. Установите Python 3.11+.
2. Запустите `start_windows.bat`. При первом запуске отредактируйте `.env`, указав настоящую организацию и email для SEC User-Agent.
3. Откройте `http://localhost:8501`.

Или в PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Веб-развёртывание

Загрузите содержимое этой папки в GitHub, выберите `app.py` при Deploy на https://share.streamlit.io и укажите `SEC_USER_AGENT` через **Advanced settings → Secrets**. Файл `.streamlit/secrets.toml.example` содержит шаблон.

## Алгоритм

1. Парсинг ISIN, CUSIP, эмитента, купона, валюты и погашения.
2. SEC Full Text Search по идентификаторам и комбинациям эмитент/купон/год.
3. Поиск SEC CIK из открытого списка тикеров или вручную указанный CIK родительской компании.
4. SEC Submissions + архивы приложений к 8-K и 6-K.
5. Загрузка кандидатов (HTML / доступные PDF) и оценка соответствия.
6. Разделение на **Primary document candidate**, **Supporting evidence**, **Unverified** и ошибки.
7. Экспорт Excel.

**Правила достоверности:** приложение не утверждает, что кандидат на Indenture точно соответствует выпуску, пока документ не проверен человеком. N-PORT, пресс-релизы и отчётность не становятся эмиссионными документами от одного наличия ISIN. SEC может блокировать облачный IP — HTTP 403/429 отличается от «не найдено».

## Технологии и структура

```text
bond-document-finder-web/
├── app.py                         # UI Streamlit
├── bondfinder/
│   ├── __init__.py
│   ├── sec.py                     # SEC HTTP/search/filings/exhibits
│   ├── matching.py                # query parsing and relevance
│   └── export.py                  # XLSX generation
├── tests/
│   ├── test_matching.py
│   └── test_efts.py
├── requirements.txt
├── sample_bonds.csv
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
├── .env.example
├── .gitignore
├── Dockerfile
├── start_windows.bat
├── run_windows.bat
├── DEPLOY_WEB_RU.md
└── TECHNICAL_SPEC_RU.md
```

## Локальные тесты

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests/requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Тестовые запросы

- `US03772CAA18` / APLD ComputeCo 2 LLC / CIK 1144879
- `US595112AN31` / Micron Technology Inc. / CIK 723125
- `Prologis Euro Finance 4% 05.05.2034 EUR`

Приложение **не содержит встроенной базы проверенных SEC-ссылок**: ссылки формируются из ответов SEC и проверяются HTTP запросами во время поиска. В локальной среде проекта выполнены модульные тесты; полноценный live-тест через SEC зависит от доступности SEC в среде размещения.
