"""Why is the chunk ceiling 510 and not 512?  (~20 seconds)

bge adds [CLS] and [SEP] itself, so a chunk counted at 512 CONTENT tokens arrives as 514 and
is truncated. Nothing raises, nothing warns.

This proves the tail contributes nothing: the full text and its 510-token prefix embed to
cosine 1.000000. A chunk stored over the ceiling would sit in the database with text the UI
displays and quotes, while its vector describes only part of it — citable but unretrievable.
"""
from sentence_transformers import SentenceTransformer
from transformers import AutoConfig, AutoTokenizer

from app.config import settings

cfg = AutoConfig.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)
tok = AutoTokenizer.from_pretrained(settings.embedding_model, revision=settings.embedding_model_revision)

print("where 512 comes from")
print(f"  architecture            : {cfg.model_type}")
print(f"  max_position_embeddings : {cfg.max_position_embeddings}  <- the model has exactly this many position vectors")

probe = "word " * 10
special = len(tok.encode(probe, add_special_tokens=True)) - len(tok.encode(probe, add_special_tokens=False))
print(f"  special tokens added    : {special}  ([CLS] and [SEP])")
print(f"  safe content ceiling    : {cfg.max_position_embeddings - special}")
print(f"  settings.max_chunk_tokens = {settings.max_chunk_tokens}")
assert settings.max_chunk_tokens == cfg.max_position_embeddings - special

model = SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision, device="cpu")
long_text = " ".join(f"alpha{i}" for i in range(400)) + " THE_TAIL_SENTENCE_IS_UNIQUE_AND_WILL_BE_LOST"
n = len(tok.encode(long_text, add_special_tokens=False))
truncated = tok.decode(tok.encode(long_text, add_special_tokens=False)[:settings.max_chunk_tokens])

a, b = model.encode([long_text, truncated], normalize_embeddings=True)
print("\nwhat truncation does")
print(f"  full text        : {n} tokens")
print(f"  model can see    : {settings.max_chunk_tokens} + {special} special")
print(f"  tail survived?   : {'THE_TAIL' in truncated}")
print(f"  cosine(full, truncated) = {float(a @ b):.6f}")
print("\n  1.000000 means the discarded tail contributed NOTHING. No error. No warning.")
