"""129/177 chunks had a nearest neighbour in the same document. Is the other 27% a weakness
of the vector space, or an artifact of the corpus containing DUPLICATE documents?

AeroTwin appears twice, the tracker four times, the assessment CSV three times. A chunk
whose twin is byte-identical will find that twin first, and it lives in a "different
document" only because the filename differs.
"""
import subprocess
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from app.config import settings
from app.ingestion import UnsupportedDocument, chunk_document, extract

UP = Path(__file__).resolve().parents[2] / "uploads"
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
count = lambda t: len(tok.encode(t, add_special_tokens=False))

rows = subprocess.run(["psql", "-d", "knowledge_assistant", "-At", "-F|", "-c",
                       "SELECT id, filename FROM documents;"], capture_output=True, text=True).stdout.strip().splitlines()
texts, docs = [], []
for line in rows:
    doc_id, name = line.split("|", 1)
    p = UP / doc_id
    if not p.exists():
        continue
    try:
        d = extract(p.read_bytes(), name)
    except UnsupportedDocument:
        continue
    if d.is_empty:
        continue
    for c in chunk_document(d, count, max_tokens=settings.max_chunk_tokens):
        texts.append(c.text); docs.append(doc_id)

V = np.array(model.encode(texts, batch_size=1, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
sims = V @ V.T
np.fill_diagonal(sims, -2)
nn = sims.argmax(axis=1)

same_doc = sum(docs[i] == docs[nn[i]] for i in range(len(docs)))
cross = [i for i in range(len(docs)) if docs[i] != docs[nn[i]]]
identical = [i for i in cross if texts[i].strip() == texts[nn[i]].strip()]

print(f"  chunks                                    : {len(texts)}")
print(f"  nearest neighbour in the same document    : {same_doc} ({same_doc/len(texts):.0%})")
print(f"  nearest neighbour in a DIFFERENT document : {len(cross)}")
print(f"    ...of which the text is IDENTICAL       : {len(identical)}  <- duplicate documents")
print(f"    ...genuinely different text             : {len(cross) - len(identical)}")
print()
print(f"  excluding duplicate-document hits: {(same_doc + len(identical))}/{len(texts)} "
      f"({(same_doc + len(identical))/len(texts):.0%}) land on their own document or an exact copy of themselves")
if len(cross) - len(identical):
    print("\n  the genuinely cross-document ones:")
    for i in [x for x in cross if x not in identical][:5]:
        print(f"    sim={sims[i][nn[i]]:.3f}  {texts[i][:46]!r}")
        print(f"              -> {texts[nn[i]][:46]!r}")
