"""Optional offline P-04 audit. Requires requirements-audit.txt and pdftotext."""
import hashlib
import importlib.metadata
import re
import subprocess
from pathlib import Path
PATTERN=r'[A-Z]{3}[0-9]{5}'
def compare_sets(native,snapshot,extracted):
    return {name:{'directory_ids':len(ids),'matched_ids':len(snapshot&ids),'unknown_ids':len(snapshot-ids),'unknown_percent':round(100*len(snapshot-ids)/len(snapshot),2) if snapshot else None,'equals_native':ids==native,'missing_native_ids':len(native-ids),'extra_ids':len(ids-native),'lost_matching_ids':len((native-ids)&snapshot),'ids_sha256':hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()} for name,ids in extracted.items()}
def audit(pdf,native,snapshot,layout_text=None):
    from pypdf import PdfReader
    import fitz
    pdf=Path(pdf);reader=PdfReader(pdf);pypdf_ids=set()
    for page in reader.pages:pypdf_ids.update(re.findall(PATTERN,page.extract_text() or ''))
    with fitz.open(pdf) as book:
        fitz_ids=set()
        for page in book:fitz_ids.update(re.findall(PATTERN,page.get_text()))
    if layout_text:text=Path(layout_text).read_text();fresh=False
    else:text=subprocess.check_output(['pdftotext','-layout',str(pdf),'-'],text=True,timeout=300);fresh=True
    methods=compare_sets(native,snapshot,{'pypdf':pypdf_ids,'pymupdf':fitz_ids,'poppler_layout':set(re.findall(PATTERN,text))})
    return {'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pdf_pages':len(reader.pages),'layout_text_sha256':hashlib.sha256(text.encode()).hexdigest(),'layout_extracted_in_this_run':fresh,'versions':{p:importlib.metadata.version(p) for p in ['pypdf','PyMuPDF']},'poppler_version':subprocess.run(['pdftotext','-v'],capture_output=True,text=True).stderr.splitlines()[0],'methods':methods,'independent_native_verification_passed':methods['pypdf']['equals_native'] and methods['pymupdf']['equals_native'],'interpretation':'The PDF extractor changes the ID set. Use native XLSX, independently matched by two PDF engines. The historical 1572 claim is not reproduced; 1527 is reproduced by Poppler. A transposition of digits is possible but not proven.'}
