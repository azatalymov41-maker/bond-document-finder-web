"""SEC EDGAR connector: Full Text Search (web endpoint) and documented Submissions API.
SEC searches are subject to SEC fair-access rules and may be blocked from cloud hosting.
"""
from __future__ import annotations
import re
import time
import threading
from datetime import datetime
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup
from .matching import (Bond, clean, evidence_score, category,
                       inferred_identifiers, status_from_evidence, tokenize_name)

EFTS = 'https://efts.sec.gov/LATEST/search-index'
SEC_ROOT = 'https://www.sec.gov'
SEC_FORMS = {'8-K', '424B2', '424B3', '424B5', '424B7', '6-K',
             'F-3', 'S-3', '10-K', '10-Q', '20-F', 'F-1', 'S-1'}
_LOCK = threading.Lock()
_LAST = [0.0]

class SECError(Exception):
    pass

class SECClient:
    def __init__(self, user_agent: str, timeout=18, min_interval=0.7):
        if not user_agent or '@' not in user_agent or 'example.com' in user_agent:
            raise ValueError('Укажите реальное имя и email для SEC User-Agent.')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'application/json,text/html,application/xhtml+xml,application/pdf,*/*',
            'Accept-Encoding': 'gzip, deflate',
        })
        self.timeout = float(timeout)
        self.min_interval = max(float(min_interval), 0.5)

    def get(self, url, params=None):
        if not re.match(r'^https://(?:www\.sec\.gov|data\.sec\.gov|efts\.sec\.gov)/', url):
            raise SECError('External URL blocked; SEC domains only')
        for attempt in range(3):
            with _LOCK:
                delay = self.min_interval - (time.monotonic() - _LAST[0])
                if delay > 0:
                    time.sleep(delay)
                _LAST[0] = time.monotonic()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code in (403, 429):
                    if attempt < 2:
                        time.sleep((attempt + 1) * 2)
                        continue
                    raise SECError(f'SEC HTTP {response.status_code}: доступ ограничен или временно заблокирован')
                if response.status_code >= 500 and attempt < 2:
                    time.sleep(attempt+1)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as error:
                if attempt == 2:
                    raise SECError(str(error)) from error
                time.sleep(attempt+1)
        raise SECError('Запрос SEC не выполнен')

    def search_efts(self, query, size=20):
        if not query:
            return []
        try:
            data = self.get(EFTS, {'q': query, 'from': 0, 'size': size}).json()
        except ValueError as error:
            raise SECError('SEC Full Text Search returned invalid JSON') from error
        results = []
        for hit in data.get('hits',{}).get('hits',[]):
            src = hit.get('_source',{})
            ciks = src.get('ciks') or []
            cik = str(ciks[0]).lstrip('0') if ciks else ''
            accession = str(src.get('adsh') or '')
            filename = str(src.get('file_name') or src.get('file') or '')
            hit_id = str(hit.get('_id',''))
            if ':' in hit_id:
                filename = hit_id.split(':',1)[1]
            filename = filename.split('/')[-1]
            safe = bool(re.fullmatch(r'[A-Za-z0-9_.-]+',filename))
            base = f'{SEC_ROOT}/Archives/edgar/data/{cik}/{accession.replace("-", "")}/'
            document_url = base+quote(filename) if cik and accession and safe else ''
            index_url = base+f'{accession}-index.htm' if cik and accession else ''
            attachment_form = ('EX-4.1' if re.search(r'(?:ex|exh|exhibit)[-_]?4(?:[-_.]|\d)', filename, re.I) else '')
            display = src.get('display_names',[])
            title = clean(' '.join(str(n) for n in display) if isinstance(display,list) else str(display))
            results.append({'title':title,'description':clean(src.get('file_description','')),
                            'form':str(src.get('form','')),
                            'filing_date':str(src.get('file_date','')),
                            'url':document_url,'index_url':index_url,
                            'cik':cik,'accession':accession,'attachment_form':attachment_form,'source':'SEC Full Text Search'})
        return results

    def company_tickers(self):
        return list(self.get('https://www.sec.gov/files/company_tickers.json').json().values())

    def company_ciks(self, issuer):
        words = tokenize_name(issuer)
        if not words:
            return []
        ranked = []
        for record in self.company_tickers():
            name = str(record.get('title',''))
            candidate_words = tokenize_name(name)
            if not candidate_words:
                continue
            intersection = len(words & candidate_words)
            if intersection >= max(1,len(words)-1):
                ranked.append((intersection/max(1,len(words)),int(record['cik_str']),name))
        ranked.sort(key=lambda x:x[0],reverse=True)
        return [{'cik':str(cik),'name':name} for _,cik,name in ranked[:3]]

    def submissions(self, cik):
        return self.get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json').json()

    def recent_filing_candidates(self, cik, limit=60, issue_date=''):
        data = self.submissions(cik)
        recent = data.get('filings',{}).get('recent',{})
        results = []
        for i, accession in enumerate(recent.get('accessionNumber',[])):
            form = recent.get('form',[])[i]
            if form not in SEC_FORMS:
                continue
            filed = recent.get('filingDate',[])[i]
            if issue_date and re.fullmatch(r'\d{4}-\d{2}-\d{2}',issue_date):
                try:
                    if abs((datetime.fromisoformat(filed)-datetime.fromisoformat(issue_date)).days)>550:
                        continue
                except ValueError:
                    pass
            primary = recent.get('primaryDocument',[])[i]
            if not re.fullmatch(r'[A-Za-z0-9_.-]+',primary):
                continue
            base = f'{SEC_ROOT}/Archives/edgar/data/{int(cik)}/{accession.replace("-", "")}/'
            results.append({'title':data.get('name',''), 'description':'',
                            'form':form,'filing_date':filed,
                            'url':base+quote(primary),
                            'index_url':base+accession+'-index.htm',
                            'source':'SEC Submissions', 'cik':str(cik), 'accession':accession})
            if len(results)>=limit:
                break
        return results

    def filing_exhibits(self, filing, limit=12):
        index_url = filing.get('index_url','')
        if not index_url:
            return []
        html = self.get(index_url).text
        soup = BeautifulSoup(html,'html.parser')
        exhibits = []
        for tr in soup.select('tr'):
            cells = tr.find_all('td')
            if len(cells)<4:
                continue
            a = tr.find('a',href=True)
            if not a:
                continue
            href = a['href']
            if not re.search(r'\.(?:htm|html|pdf)$',href,re.I):
                continue
            description = ' '.join(c.get_text(' ',strip=True) for c in cells)
            if not re.search(r'EX[- ]?4\b|indenture|prospectus|form of note|pricing supplement|424B|offering|final terms',description,re.I):
                continue
            url = urljoin(index_url,href)
            # SEC archive only, never follow arbitrary links from filing HTML.
            if not url.startswith('https://www.sec.gov/Archives/'):
                continue
            typ = clean(cells[3].get_text(' ',strip=True)) if len(cells)>3 else ''
            exhibits.append({**filing,'title':description[:220],
                             'description':description[:220],
                             'form':typ if typ.startswith('EX-') else filing.get('form',''),
                             'url':url,'source':'SEC Exhibit'})
        return exhibits[:limit]

    def inspect(self,bond,candidate,max_chars=350000):
        url = candidate.get('url','')
        if not url or not url.startswith('https://www.sec.gov/Archives/'):
            return {**candidate,'score':0,'evidence':[], 'status':'URL unavailable',
                    'document_type':'Unknown'}
        try:
            response = self.get(url)
            content_type = response.headers.get('Content-Type','')
            if 'pdf' in content_type or url.lower().endswith('.pdf'):
                import fitz
                # Avoid keeping oversized PDFs in memory.
                if len(response.content) > 12_000_000:
                    return {**candidate,'score':0,'evidence':[], 'status':'PDF too large for automatic review',
                            'document_type':'PDF / manual review'}
                pdf = fitz.open(stream=response.content,filetype='pdf')
                body = ' '.join(page.get_text() for page in list(pdf)[:60])[:max_chars]
                pdf.close()
            else:
                soup = BeautifulSoup(response.content,'html.parser')
                for tag in soup(['script','style','noscript']):tag.decompose()
                body = soup.get_text(' ',strip=True)[:max_chars]
            heading = clean(candidate.get('title','')+' '+candidate.get('description',''))
            score,evidence = evidence_score(bond,body,heading,candidate.get('form',''))
            kind = category(heading,candidate.get('attachment_form') or candidate.get('form',''),body)
            return {**candidate,'score':score,'evidence':evidence,
                    'status':status_from_evidence(evidence,kind,candidate.get('form','')),
                    'document_type':kind,'excerpt':body[:500]}
        except (SECError,ValueError,ImportError,RuntimeError) as error:
            return {**candidate,'score':0,'evidence':[],
                    'status':'Fetch failed / blocked', 'error':str(error)[:200],
                    'document_type':'Unknown'}


def build_queries(bond):
    inferred_identifiers(bond)
    queries=[]
    if bond.isin:queries.append('"'+bond.isin+'"')
    if bond.cusip:queries.append('"'+bond.cusip+'"')
    if bond.issuer:
        issuer=clean(bond.issuer)
        queries.append('"'+issuer+'"')
        if bond.coupon:queries.append('"'+issuer+'" "'+str(bond.coupon).replace('%','')+'"')
        if bond.maturity:queries.append('"'+issuer+'" "'+bond.maturity[:4]+'"')
    if bond.query and not bond.issuer:
        queries.append(bond.query)
    return list(dict.fromkeys(queries))[:7]


def run_search(client,bond,max_queries=5,max_inspect=14,progress=None):
    inferred_identifiers(bond)
    if not any((bond.query,bond.isin,bond.cusip,bond.issuer,bond.cik)):
        return [],[],['No search criteria provided']
    logs=[];errors=[];candidates=[]
    def log(msg):
        logs.append(msg)
        if progress:progress(msg)
    for query in build_queries(bond)[:max_queries]:
        log('SEC full-text search: '+query)
        try:
            candidates.extend(client.search_efts(query,size=20))
        except (SECError,ValueError,KeyError) as error:
            errors.append(f'Full Text Search {query}: {error}')
    ciks=[]
    if bond.cik and re.fullmatch(r'\d{1,10}',bond.cik):
        ciks=[bond.cik]
    elif bond.issuer:
        try:
            ciks=[entry['cik'] for entry in client.company_ciks(bond.issuer)]
            if ciks:log('CIK: '+', '.join(ciks))
        except (SECError,ValueError) as error:
            errors.append('Issuer CIK lookup: '+str(error))
    for cik in ciks[:2]:
        try:
            filings = client.recent_filing_candidates(cik,limit=45,issue_date=bond.issue_date)
            candidates.extend(filings)
            exhibit_count=0
            for filing in filings:
                if filing['form'] in {'8-K','6-K'}:
                    try:
                        candidates.extend(client.filing_exhibits(filing))
                        exhibit_count+=1
                        if exhibit_count>=12:
                            break
                    except SECError as error:
                        errors.append(f'Exhibits for accession {filing["accession"]}: {error}')
        except (SECError,ValueError) as error:
            errors.append('SEC Submissions '+cik+': '+str(error))
    unique=[];seen=set()
    for row in candidates:
        url=row.get('url','')
        if url and url not in seen:
            seen.add(url);unique.append(row)
    def rank(row):
        title=(row.get('title','')+' '+row.get('description','')).lower()
        priority=40 if row.get('source')=='SEC Exhibit' else 25 if row.get('source')=='SEC Full Text Search' else 0
        priority+=25 if re.search(r'indenture|form of note|prospectus|ex[- ]?4',title,re.I) else 0
        if bond.issuer:
            words=tokenize_name(bond.issuer)
            priority+=5*len(words & tokenize_name(title))
        return priority
    unique.sort(key=rank,reverse=True)
    matches=[]
    for n,row in enumerate(unique[:max_inspect]):
        log(f'Inspecting {n+1}/{min(len(unique),max_inspect)}: '+row['url'])
        matches.append(client.inspect(bond,row))
    matches.sort(key=lambda row:(row.get('status','').startswith('Primary'),row.get('score',0)),reverse=True)
    if not unique:
        errors.append('Нет кандидатов по выбранным запросам; это не означает, что документа не существует.')
    if unique and not matches:
        errors.append('Candidates were retrieved but none could be inspected.')
    return matches,logs,errors
