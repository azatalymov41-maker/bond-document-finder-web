"""Bond Document Finder — web-first Streamlit SEC EDGAR search MVP.
Deploy on Streamlit Community Cloud with a real SEC_USER_AGENT secret.
"""
from pathlib import Path
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from bondfinder.matching import Bond, extract_bond_from_query, normalize_date
from bondfinder.sec import SECClient, SECError, run_search
from bondfinder.export import excel_bytes

load_dotenv(Path(__file__).with_name('.env'))
st.set_page_config(page_title='Bond Document Finder',page_icon='📄',layout='wide')

# Keep configuration in Streamlit Cloud secrets; allow a temporary browser-session
# contact identity only as a fallback for local testing.
def config(name, default=''):
    value=os.getenv(name)
    if value:return value
    try:
        return st.secrets.get(name,default)
    except (FileNotFoundError,RuntimeError,AttributeError):
        return default

st.markdown('''<style>
.block-container{padding-top:2rem;max-width:1200px}
[data-testid="stMetric"]{border:1px solid #E0E8F0;padding:12px;border-radius:12px}
</style>''',unsafe_allow_html=True)

st.title('📄 Bond Document Finder')
st.caption('SEC EDGAR · поиск по ISIN, CUSIP или описанию выпуска · проверка кандидатов · Excel')
with st.sidebar:
    st.header('⚙️ Настройки поиска')
    default_agent=config('SEC_USER_AGENT')
    if default_agent and '@' in default_agent and 'your-real-domain' not in default_agent:
        st.success('SEC User-Agent настроен')
        agent=default_agent
    else:
        st.info('Укажите настоящее имя/организацию и email для обращения к SEC. Для публичного сайта добавьте это значение в Streamlit Secrets.')
        agent=st.text_input('SEC User-Agent (текущая сессия)',placeholder='Company BondFinder contact@company.com',type='default')
    max_inspect=st.slider('Максимум документов для проверки',4,30,12)
    max_queries=st.slider('Поисковых запросов',1,7,5)
    st.caption('SEC Fair Access: запросы ограничены и выполняются с задержкой. Некоторые облачные серверы могут получать HTTP 403.')
    st.markdown('[SEC EDGAR](https://www.sec.gov/edgar/search/) · [SEC Developer Resources](https://www.sec.gov/about/developer-resources)')


def sec_client():
    return SECClient(agent, timeout=float(config('SEC_TIMEOUT','18')),
                     min_interval=float(config('SEC_MIN_INTERVAL','0.7')))


def output_row(bond,result,extra_error=''):
    return {
        'query':bond.query or bond.isin or bond.issuer,
        'isin':bond.isin,'cusip':bond.cusip,'issuer':bond.issuer,
        'coupon':bond.coupon,'maturity':bond.maturity,'currency':bond.currency,
        'document_type':result.get('document_type',''),
        'status':result.get('status',''), 'score':result.get('score',0),
        'url':result.get('url',''),'index_url':result.get('index_url',''),
        'evidence':'; '.join(result.get('evidence',[])),
        'source':result.get('source',''), 'form':result.get('form',''),
        'filing_date':result.get('filing_date',''),
        'error':extra_error or result.get('error',''),
        'excerpt':result.get('excerpt',''),
    }


def render_results(rows,logs,errors,heading='Результаты'):
    st.subheader(heading)
    if not rows:
        st.warning('По текущему поиску нет проверенных кандидатов. Проверьте журнал: SEC мог ограничить доступ.')
    else:
        primary=sum(str(r.get('status','')).startswith('Primary') for r in rows)
        supporting=sum(str(r.get('status','')).startswith('Supporting') for r in rows)
        c1,c2,c3=st.columns(3)
        c1.metric('Всего просмотрено',len(rows))
        c2.metric('Кандидатов на первичный документ',primary)
        c3.metric('Подтверждающих материалов',supporting)
        st.caption('Важно: Primary document candidate ≠ подтверждённый документ. Балл — эвристическая релевантность, не вероятность.')
        display=pd.DataFrame(rows)
        cols=['query','document_type','status','score','url','form','filing_date','evidence']
        st.dataframe(display[[c for c in cols if c in display]],hide_index=True,use_container_width=True,
                     column_config={'url':st.column_config.LinkColumn('SEC документ'),
                                    'score':st.column_config.NumberColumn('Score / 100')})
        st.download_button('⬇ Скачать результаты (Excel)',excel_bytes(rows),
                           file_name='bond_document_finder_results.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        with st.expander('🔍 Подробности найденных документов'):
            for i,r in enumerate(rows[:20],1):
                st.markdown(f'**{i}. {r.get("document_type") or "SEC filing"} — {r.get("score",0)}/100**')
                st.write('Статус:',r.get('status',''))
                if r.get('url'):st.link_button('Открыть документ SEC',r['url'])
                if r.get('evidence'):st.caption('Признаки: '+r['evidence'])
                if r.get('excerpt'):st.caption('Начало документа: '+r['excerpt'][:300])
                if r.get('error'):st.error(r['error'])
                st.divider()
    if errors:
        with st.expander(f'⚠️ Ошибки и ограничения ({len(errors)})',expanded=not bool(rows)):
            for e in errors:st.warning(e)
    with st.expander(f'Журнал поиска ({len(logs)})'):
        st.code('\n'.join(logs) or 'Запросы не выполнялись',language='text')


single,batch,guide=st.tabs(['🔎 Поиск одной облигации','📊 Поиск по Excel/CSV','ℹ️ Как пользоваться'])
with single:
    with st.form('single_bond'):
        query=st.text_input('ISIN / CUSIP / название и параметры выпуска',
                            placeholder='Например: Prologis Euro Finance 4% 05.05.2034 EUR или US03772CAA18')
        with st.expander('Дополнительные параметры (повышают точность)'):
            a,b=st.columns(2)
            with a:
                isin=st.text_input('ISIN',placeholder='US03772CAA18')
                cusip=st.text_input('CUSIP',placeholder='03772CAA1')
                issuer=st.text_input('Полное юридическое название эмитента',placeholder='APLD ComputeCo 2 LLC')
                cik=st.text_input('SEC CIK эмитента или материнской компании',placeholder='1144879')
            with b:
                coupon=st.text_input('Coupon, %',placeholder='6.750')
                maturity=st.text_input('Maturity, YYYY-MM-DD',placeholder='2031-03-15')
                issue_date=st.text_input('Issue date, YYYY-MM-DD (опционально)',placeholder='2026-03-10')
                currency=st.text_input('Currency',placeholder='USD')
        search=st.form_submit_button('🔎 Найти документы в SEC',type='primary',use_container_width=True)
    if search:
        parsed=extract_bond_from_query(query)
        bond=Bond(query=query,isin=(isin.strip() or parsed.isin).upper(),
                  cusip=(cusip.strip() or parsed.cusip).upper(),
                  issuer=issuer.strip() or parsed.issuer,
                  coupon=coupon.strip() or parsed.coupon,
                  maturity=normalize_date(maturity) if maturity else parsed.maturity,
                  currency=(currency.strip() or parsed.currency).upper(),
                  cik=cik.strip(),issue_date=normalize_date(issue_date))
        st.caption(f'Распознан запрос: эмитент «{bond.issuer or "—"}», ISIN {bond.isin or "—"}, '
                   f'купон {bond.coupon or "—"}, погашение {bond.maturity or "—"}, CIK {bond.cik or "—"}')
        if not (bond.query or bond.isin or bond.cusip or bond.issuer):
            st.error('Введите ISIN, CUSIP или описание выпуска.')
        else:
            try:
                client=sec_client()
                status=st.empty()
                with st.spinner('SEC: поиск filings и приложений…'):
                    results,logs,errors=run_search(client,bond,max_queries,max_inspect,
                        progress=lambda message:status.caption(message))
                status.empty()
                st.session_state['single_results']=([output_row(bond,r) for r in results],logs,errors)
            except (ValueError,SECError) as e:
                st.error('Не удалось выполнить поиск: '+str(e))
    if 'single_results' in st.session_state:
        render_results(*st.session_state['single_results'])

with batch:
    st.write('Загрузите Excel/CSV с колонками `ISIN`, `CUSIP`, `Issuer`, `Coupon`, `Maturity`, `CIK` или `Query`. Допустимы частично заполненные строки.')
    st.caption('Для облачного MVP рекомендуются небольшие пакеты: SEC может ограничить длительные автоматические запросы.')
    uploaded=st.file_uploader('Выберите файл',type=['xlsx','csv'],key='batch_file')
    max_rows=st.number_input('Максимальное количество строк',min_value=1,max_value=50,value=10)
    if uploaded is not None:
        try:
            frame=(pd.read_excel(uploaded,dtype=str).fillna('') if uploaded.name.endswith('.xlsx')
                   else pd.read_csv(uploaded,dtype=str).fillna(''))
            st.dataframe(frame.head(10),hide_index=True,use_container_width=True)
            if st.button('▶ Поиск по списку',type='primary'):
                if len(frame)>int(max_rows):
                    st.info(f'Будут обработаны первые {int(max_rows)} строк из {len(frame)}.')
                client=sec_client()
                columns={str(k).strip().lower():k for k in frame.columns}
                all_rows=[];all_logs=[];all_errors=[]
                progress=st.progress(0)
                for index,(_,values) in enumerate(frame.head(int(max_rows)).iterrows()):
                    def field(*names):
                        for name in names:
                            if name in columns:
                                return str(values[columns[name]]).strip()
                        return ''
                    phrase=field('query','description','bond')
                    parsed=extract_bond_from_query(phrase)
                    bond=Bond(query=phrase, isin=(field('isin') or parsed.isin).upper(),
                              cusip=(field('cusip') or parsed.cusip).upper(),
                              issuer=field('issuer','emitter','emitent') or parsed.issuer,
                              coupon=field('coupon','coupon rate') or parsed.coupon,
                              maturity=normalize_date(field('maturity','maturity date')) or parsed.maturity,
                              currency=field('currency') or parsed.currency,
                              cik=field('cik'),issue_date=normalize_date(field('issue date','issue_date')))
                    try:
                        findings,logs,errors=run_search(client,bond,
                            max_queries=min(max_queries,3),max_inspect=min(max_inspect,7))
                        all_rows.extend(output_row(bond,r) for r in findings)
                        if not findings:
                            all_rows.append(output_row(bond,{'status':'No verified candidates / check errors'}))
                        all_logs.extend(f'#{index+1}: {line}' for line in logs)
                        all_errors.extend(f'#{index+1}: {error}' for error in errors)
                    except Exception as e:
                        all_rows.append(output_row(bond,{'status':'Search error'},str(e)))
                        all_errors.append(f'#{index+1}: {e}')
                    progress.progress((index+1)/min(len(frame),int(max_rows)))
                st.session_state['batch_results']=(all_rows,all_logs,all_errors)
        except Exception as e:
            st.error(f'Не удалось прочитать файл или запустить поиск: {e}')
    if 'batch_results' in st.session_state:
        render_results(*st.session_state['batch_results'],heading='Пакетные результаты')

with guide:
    st.markdown('''
    **Как получить наиболее точные результаты:**
    1. Начните с ISIN. При его отсутствии введите юридическое название эмитента, купон и дату погашения.
    2. Для SPV-выпусков укажите **CIK материнской компании** — он помогает искать 8-K и Exhibit 4.
    3. Если SEC не возвращает результат, откройте «Ошибки и ограничения». HTTP 403/429 — блокировка доступа, а не отсутствие облигации.
    4. Документ со статусом **Primary document candidate — review** необходимо открыть и проверить вручную.

    **Доступные источники в MVP:** SEC Full Text Search, SEC Submissions и приложения к filings. Международные источники, базы данных с платным доступом и AI-верификация пока не подключены.

    **Безопасность:** не вводите персональные логины и API-ключи в поисковые поля. Для облачного размещения используйте Streamlit Secrets.
    ''')
st.divider()
st.caption('Beta / SEC-only. Приложение не гарантирует обнаружение документов частных размещений Rule 144A. Баллы релевантности не заменяют проверку оригинала.')
