"""Excel export for SEC results (formula-injection safe)."""
from io import BytesIO
import pandas as pd

COLUMNS = ['query','isin','cusip','issuer','coupon','maturity','currency',
           'document_type','status','score','url','index_url','evidence',
           'source','form','filing_date','error','excerpt']

def excel_bytes(rows):
    frame=pd.DataFrame(rows)
    for column in COLUMNS:
        if column not in frame:
            frame[column]=''
    frame=frame[COLUMNS].copy()
    for column in frame.columns:
        frame[column]=frame[column].map(
            lambda value: "'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value
        )
    output=BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        frame.to_excel(writer,sheet_name='SEC Search Results',index=False)
        ws=writer.sheets['SEC Search Results']
        ws.freeze_panes='A2'
        ws.auto_filter.ref=ws.dimensions
        for col in ws.columns:
            letter=col[0].column_letter
            ws.column_dimensions[letter].width=min(60,max(13,len(str(col[0].value or ''))+10))
    return output.getvalue()
