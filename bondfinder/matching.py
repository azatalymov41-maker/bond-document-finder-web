"""Parsing and conservative bond/document matching. No network or LLM required."""
import re
from dataclasses import dataclass
from datetime import datetime

LEGAL = {'inc', 'incorporated', 'corp', 'corporation', 'llc', 'ltd', 'limited',
         'company', 'co', 'the', 'sa', 'plc', 'finance', 'financing', 'nv', 'lp', 'ab', 'ag'}
SUPPORT_FORMS = {'NPORT-P', 'NPORT-EX', 'N-PORT', '13F-HR', 'N-MFP3', 'N-MFP2'}
PRIMARY_MARKERS = ('indenture', 'supplemental indenture', 'prospectus supplement',
                   'pricing supplement', 'final terms', 'offering memorandum',
                   'offering circular', 'form of note', "officers' certificate")


@dataclass
class Bond:
    query: str = ''
    isin: str = ''
    cusip: str = ''
    issuer: str = ''
    coupon: str = ''
    maturity: str = ''
    currency: str = ''
    cik: str = ''
    issue_date: str = ''


def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def normalize_date(value):
    value = clean(value)
    if not value:
        return ''
    value = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', value, flags=re.I)
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y',
                '%d %b %Y', '%d %B %Y', '%d%b%Y', '%d%B%Y',
                '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return value


def maturity_variants(value):
    date = normalize_date(value)
    try:
        d = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return [date] if date else []
    return [d.strftime('%Y-%m-%d'), d.strftime('%Y'),
            f'{d.strftime("%B")} {d.day}, {d.year}',
            f'{d.strftime("%b")} {d.day}, {d.year}',
            f'{d.day} {d.strftime("%B")} {d.year}',
            f'{d.day} {d.strftime("%b")} {d.year}',
            d.strftime('%m/%d/%Y'), d.strftime('%d/%m/%Y')]


def coupon_variants(value):
    value = clean(value).replace('%', '').replace(',', '.')
    try:
        f = float(value)
        return [f'{f:g}', f'{f:.2f}', f'{f:.3f}', f'{f:.4f}']
    except ValueError:
        return [value] if value else []


def inferred_identifiers(bond):
    bond.isin = clean(bond.isin).upper()
    bond.cusip = clean(bond.cusip).upper()
    if bond.isin.startswith('US') and len(bond.isin) == 12 and not bond.cusip:
        bond.cusip = bond.isin[2:11]
    return bond


def tokenize_name(text):
    return {w for w in re.findall(r'[a-z0-9]+', clean(text).lower())
            if len(w) > 1 and w not in LEGAL}


def extract_bond_from_query(query):
    """Best-effort parsing only; never claim parsed data are externally verified."""
    q = clean(query)
    isin_match = re.search(r'(?<![A-Z0-9])([A-Z]{2}[A-Z0-9]{9}\d)(?![A-Z0-9])', q, re.I)
    cusip_match = re.search(r'(?<![A-Z0-9])([A-Z0-9]{8}\d)(?![A-Z0-9])', q, re.I)
    isin = isin_match.group(1).upper() if isin_match else ''
    cusip = cusip_match.group(1).upper() if cusip_match and not isin else ''
    rest = re.sub(re.escape(isin), ' ', q, flags=re.I) if isin else q
    if cusip:
        rest = re.sub(re.escape(cusip), ' ', rest, flags=re.I)
    coupon_match = re.search(r'(?<![\d.])(\d{1,2}(?:[.,]\d{1,4})?)\s*%', rest)
    if not coupon_match:
        coupon_match = re.search(r'(?<![\d.])(\d{1,2}[.,]\d{1,4})\b(?=\s+\d{1,2}\s*[A-Za-z]{3}|\s+20\d{2})', rest)
    coupon = coupon_match.group(1).replace(',', '.') if coupon_match else ''
    date_match = re.search(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{4}\b|\b\d{1,2}\s*[a-zA-Z]{3,9}\s*20\d{2}\b',rest,re.I)
    maturity = normalize_date(date_match.group(0)) if date_match else ''
    if not maturity:
        year_match = re.search(r'\b(20\d{2}|19\d{2})\b',rest)
        maturity = year_match.group(1) if year_match else ''
    currency_match = re.search(r'\b(USD|EUR|GBP|AUD|CAD|CHF|JPY|SEK|NOK)\b',rest,re.I)
    currency = currency_match.group(1).upper() if currency_match else ''
    issuer = rest
    if coupon_match:
        issuer = issuer.replace(coupon_match.group(0), ' ', 1)
    if date_match:
        issuer = issuer.replace(date_match.group(0), ' ', 1)
    elif maturity:
        issuer = re.sub(r'\b'+re.escape(maturity)+r'\b',' ',issuer,count=1)
    if currency:
        issuer = re.sub(r'\b'+currency+r'\b',' ',issuer,flags=re.I)
    issuer = re.sub(r'\b(FRN|fixed|notes|bonds|senior|secured|due|conv)\b',' ',issuer,flags=re.I)
    issuer = clean(issuer.strip(',;-–()# '))
    return Bond(query=q, isin=isin, cusip=cusip, issuer=issuer, coupon=coupon,
                maturity=maturity, currency=currency)


def evidence_score(bond, text, title='', form=''):
    """Evidence and heuristic relevance, NOT an externally verified confidence score."""
    corpus = (clean(title) + ' ' + clean(text)).lower()
    score = 0
    evidence = []
    if bond.isin and re.search(r'(?<![a-z0-9])'+re.escape(bond.isin.lower())+r'(?![a-z0-9])',corpus):
        score += 52
        evidence.append('Exact ISIN')
    if bond.cusip and re.search(r'(?<![a-z0-9])'+re.escape(bond.cusip.lower())+r'(?![a-z0-9])',corpus):
        score += 40
        evidence.append('Exact CUSIP')
    words = tokenize_name(bond.issuer)
    if words and len(words & tokenize_name(corpus[:120000])) >= max(1, len(words)-1):
        score += 12
        evidence.append('Issuer tokens')
    if bond.coupon and any(re.search(r'(?<!\d)'+re.escape(v)+r'\s*%', corpus) for v in coupon_variants(bond.coupon)):
        score += 15
        evidence.append('Coupon')
    if bond.maturity:
        variants = maturity_variants(bond.maturity)
        full_variants = [v for v in variants if len(v) > 4]
        if any(v.lower() in corpus for v in full_variants):
            score += 17
            evidence.append('Exact maturity date')
        elif variants and variants[0] and variants[0][:4] in corpus and len(variants[0]) >= 4:
            score += 6
            evidence.append('Maturity year only')
    if bond.currency and re.search(r'\b'+re.escape(bond.currency.lower())+r'\b', corpus):
        score += 3
        evidence.append('Currency')
    if form.upper() in SUPPORT_FORMS:
        score -= 30
        evidence.append('Portfolio disclosure, not issuance document')
    return max(0, min(100,score)), evidence


def category(title, form='', excerpt=''):
    """Classify using the filing's actual document/attachment heading first.
    Never classify 8-K as an indenture just because its body mentions one.
    """
    form = clean(form).upper()
    if form in SUPPORT_FORMS:
        return 'Supporting evidence (fund holding)'
    heading = clean(title).lower()
    leading = clean(excerpt)[:1600].lower()
    # For legal exhibits we can examine the opening text; for generic filings don't.
    source = heading + (' ' + leading if form.startswith('EX-4') or form == 'EX-10' else '')
    for marker,label in [
        ('supplemental indenture','Supplemental Indenture'),
        ('pricing supplement','Pricing Supplement'),
        ('prospectus supplement','Prospectus Supplement'),
        ('offering memorandum','Offering Memorandum'),
        ('offering circular','Offering Circular'),
        ('final terms','Final Terms'),
        ("officers' certificate", "Officers' Certificate"),
        ('form of note','Form of Note'),
        ('indenture','Indenture'),
    ]:
        if marker in source:
            return label
    if form in {'424B2','424B3','424B5','424B7'}:
        return 'Prospectus / 424B filing'
    if form.startswith('EX-4'):
        return 'EX-4 legal exhibit'
    return 'Other SEC filing'


def status_from_evidence(evidence, document_type, form=''):
    exact_id = any(e in evidence for e in ('Exact ISIN','Exact CUSIP'))
    full_bond = 'Issuer tokens' in evidence and 'Coupon' in evidence and 'Exact maturity date' in evidence
    legal = document_type not in ('Other SEC filing','Supporting evidence (fund holding)')
    if legal and (exact_id or full_bond):
        return 'Primary document candidate — review'
    if exact_id or full_bond:
        return 'Supporting evidence / review'
    return 'Unverified candidate'
