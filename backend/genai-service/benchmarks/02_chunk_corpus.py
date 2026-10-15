"""Day 3 verification: chunk the REAL 21 documents with the REAL bge tokenizer."""
import subprocess
from pathlib import Path

from transformers import AutoTokenizer

from app.config import settings
from app.ingestion import UnsupportedDocument, chunk_document, extract

UP = Path(__file__).resolve().parents[2] / "uploads"
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)

def count_tokens(text: str) -> int:
    return len(tok.encode(text, add_special_tokens=False))

rows = subprocess.run(
    ["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
     "SELECT id, filename FROM documents ORDER BY size_bytes DESC;"],
    capture_output=True, text=True).stdout.strip().splitlines()

print(f"{'filename':<44}{'kind':<10}{'chunks':>7}{'max':>6}{'mean':>6}  sections/pages")
print("-" * 104)
total_chunks = empty = unsupported = over = 0
all_tokens = []
for line in rows:
    doc_id, name = line.split("|")
    path = UP / doc_id
    if not path.exists():
        print(f"{name[:42]:<44}{'NO FILE':<10}"); continue
    try:
        doc = extract(path.read_bytes(), name)
    except UnsupportedDocument as e:
        unsupported += 1
        print(f"{name[:42]:<44}{'REJECT':<10}{'-':>7}{'-':>6}{'-':>6}  {e}"[:104]); continue
    if doc.is_empty:
        empty += 1
        print(f"{name[:42]:<44}{doc.kind:<10}{0:>7}{'-':>6}{'-':>6}  EMPTY -> Spring marks failed"); continue

    chunks = chunk_document(doc, count_tokens, max_tokens=settings.max_chunk_tokens)
    toks = [c.token_count for c in chunks]
    all_tokens += toks
    total_chunks += len(chunks)
    over += sum(t > settings.max_chunk_tokens for t in toks)
    labels = {c.section for c in chunks if c.section} or {f"p{c.page}" for c in chunks if c.page}
    meta = f"{len(labels)} distinct" if labels else "none"
    # every offset must resolve back to the exact chunk text
    assert all(doc.full_text[c.char_start:c.char_end] == c.text for c in chunks), f"offsets lie in {name}"
    print(f"{name[:42]:<44}{doc.kind:<10}{len(chunks):>7}{max(toks):>6}{sum(toks)//len(toks):>6}  {meta}")

print("-" * 104)
print(f"  {total_chunks} chunks from {len(rows)} documents | empty {empty} | rejected {unsupported}")
print(f"  token ceiling {settings.max_chunk_tokens}, exceeded by {over} chunks")
if all_tokens:
    s = sorted(all_tokens)
    print(f"  tokens per chunk: min {s[0]} median {s[len(s)//2]} p90 {s[int(len(s)*0.9)]} max {s[-1]}")
    print(f"  mean fill: {sum(s)/len(s)/settings.max_chunk_tokens:.0%} of the 512 ceiling")
print("  ALL char offsets verified against full_text")
