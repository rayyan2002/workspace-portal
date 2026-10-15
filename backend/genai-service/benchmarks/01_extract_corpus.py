"""What actually comes out of the 21 real documents? Not the uploads/ litter — the DB rows."""
import csv
import io
import subprocess
from pathlib import Path

UP = Path(__file__).resolve().parents[2] / "uploads"
rows = subprocess.run(
    ["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
     "SELECT id, filename, content_type, size_bytes FROM documents ORDER BY size_bytes DESC;"],
    capture_output=True, text=True).stdout.strip().splitlines()

def extract(path: Path, name: str):
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    head = path.read_bytes()[:8] if path.exists() else b""
    if head.startswith(b"%PDF"):
        from pypdf import PdfReader
        r = PdfReader(str(path))
        text = "\n".join((p.extract_text() or "") for p in r.pages)
        return f"pdf({len(r.pages)}p)", text
    if head.startswith(b"PK"):
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        out = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c is not None]
                if cells:
                    out.append(" | ".join(cells))
        return f"xlsx({len(wb.worksheets)} sheets)", "\n".join(out)
    raw = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else ""
    if ext == "csv":
        reader = csv.reader(io.StringIO(raw))
        return "csv", "\n".join(" | ".join(r) for r in reader if any(r))
    return ext or "text", raw

print(f"{'filename':<46}{'kind':<16}{'chars':>9}{'words':>8}  verdict")
print("-" * 100)
for line in rows:
    doc_id, name, ctype, size = line.split("|")
    path = UP / doc_id
    if not path.exists():
        print(f"{name[:44]:<46}{'NO FILE':<16}{'-':>9}{'-':>8}  storage_path points at nothing")
        continue
    try:
        kind, text = extract(path, name)
    except Exception as e:
        print(f"{name[:44]:<46}{'ERROR':<16}{'-':>9}{'-':>8}  {type(e).__name__}: {e}"[:130])
        continue
    text = text.strip()
    words = len(text.split())
    if words == 0:
        verdict = "EMPTY — needs OCR or is unextractable"
    elif words < 20:
        verdict = "almost nothing"
    else:
        verdict = "ok"
    print(f"{name[:44]:<46}{kind:<16}{len(text):>9}{words:>8}  {verdict}")
