"""When does a vector index start earning its place?  (~5 minutes)

V18 ships with NO vector index. At 177 rows a sequential scan beats any index, and ivfflat
builds its clusters from the data present — at this size they would be noise. This measures
where that stops being true, on THIS hardware, so an index arrives in its own migration when
a number says so rather than because it is conventional.

Runs against a SCRATCH database, created and dropped here. Half a million synthetic vectors
have no business in the real schema.

Three things measured, and the second matters more than the first:
  SPEED   query latency, exact vs index
  RECALL  ivfflat and hnsw are APPROXIMATE. If the true nearest vector sits in a cluster the
          index did not search, you never see it and nothing says so.
  BUILD   an index is not free to create, and must be rebuilt as data grows.
"""
import subprocess
import time

import numpy as np
import psycopg
from psycopg import sql

DB = "ka_index_bench"
DIM = 384
SIZES = (1_000, 10_000, 50_000)
TOP_K = 5
QUERIES = 20
CLUSTERS = 60      # vectors are drawn from this many Gaussian centres...
SPREAD = 0.35      # ...with this much noise, to imitate real embedding geometry

subprocess.run(["dropdb", "--if-exists", DB], check=False)
subprocess.run(["createdb", DB], check=True)
print(f"scratch database {DB} created")
print(f"vectors drawn from {CLUSTERS} clusters (spread {SPREAD}) — NOT uniform random;\nuniform random 384-d vectors are equidistant and make any ANN index look broken\n")


def make_centres(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    c = rng.normal(size=(CLUSTERS, DIM))
    return c / np.linalg.norm(c, axis=1, keepdims=True)


def around(centres: np.ndarray, n: int, seed: int) -> np.ndarray:
    """Vectors scattered around SHARED cluster centres.

    Two bugs were found here, and both produced confident nonsense rather than an error.

    FIRST: the data was uniformly random. In 384 dimensions random vectors are all nearly
    equidistant, so there is no structure for an approximate index to exploit — the
    benchmark generated data with none and then reported that clustering did not work.

    SECOND, and subtler: clustering was added, but `centres` were regenerated inside this
    function from its own seed. Data and queries therefore came from 60 DIFFERENT sets of
    centres, which relative to one another is still uniform random. Recall moved 19% -> 24%
    and I nearly published that as "clustering does not help".

    Centres are now made ONCE per corpus size and shared, so a query lands near real
    content — which is the entire premise of retrieval.
    """
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(centres), size=n)
    v = (centres[pick] + rng.normal(scale=SPREAD, size=(n, DIM))).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def literal(v) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def timed_query(cur, vec, use_index: bool) -> tuple[list[int], float]:
    # SET LOCAL is a utility statement: it does NOT accept bind parameters ("syntax error
    # at or near $1"). Interpolated literally, which is safe because the value is a fixed
    # on/off decided here, never user input.
    # Two literal statements rather than one f-string: psycopg types `query` as
    # LiteralString | SQL precisely so a runtime-built string cannot be passed by accident.
    if use_index:
        cur.execute("SET LOCAL enable_seqscan = off")
    else:
        cur.execute("SET LOCAL enable_seqscan = on")
    t0 = time.perf_counter()
    cur.execute("SELECT id FROM vecs ORDER BY embedding <#> %s::vector LIMIT %s", (literal(vec), TOP_K))
    ids = [r[0] for r in cur.fetchall()]
    return ids, (time.perf_counter() - t0) * 1000


with psycopg.connect(f"dbname={DB}") as conn:
    conn.execute("CREATE EXTENSION vector")
    conn.commit()

    print(f"{'rows':>8}{'exact ms':>10}{'ivfflat ms':>12}{'recall':>9}{'build s':>9}"
          f"{'hnsw ms':>10}{'recall':>9}{'build s':>9}")
    print("-" * 76)

    for n in SIZES:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS vecs")
            cur.execute(sql.SQL("CREATE TABLE vecs (id serial PRIMARY KEY, embedding vector({}))")
                        .format(sql.Literal(DIM)))
            conn.commit()

            centres = make_centres(seed=n)
            data = around(centres, n, seed=n)
            with cur.copy("COPY vecs (embedding) FROM STDIN") as copy:
                for row in data:
                    copy.write_row([literal(row)])
            conn.commit()
            cur.execute("ANALYZE vecs")

            # SAME centres as the data — a real question lands near real content.
            queries = around(centres, QUERIES, seed=999)

            truth, exact_ms = [], []
            for q in queries:
                ids, ms = timed_query(cur, q, use_index=False)
                truth.append(set(ids))
                exact_ms.append(ms)

            results = {}
            for kind, ddl in (
                ("ivfflat", sql.SQL("CREATE INDEX ON vecs USING ivfflat (embedding vector_ip_ops) "
                                    "WITH (lists = {})").format(sql.Literal(max(1, n // 1000)))),
                ("hnsw", sql.SQL("CREATE INDEX ON vecs USING hnsw (embedding vector_ip_ops)")),
            ):
                cur.execute("DROP INDEX IF EXISTS vecs_embedding_idx")
                conn.commit()
                t0 = time.perf_counter()
                cur.execute(ddl)
                conn.commit()
                build = time.perf_counter() - t0

                ms, hits = [], 0
                for q, want in zip(queries, truth, strict=True):
                    ids, t = timed_query(cur, q, use_index=True)
                    ms.append(t)
                    hits += len(set(ids) & want)
                results[kind] = (float(np.median(ms)), hits / (QUERIES * TOP_K), build)

            iv, hn = results["ivfflat"], results["hnsw"]
            print(f"{n:>8}{np.median(exact_ms):>10.1f}{iv[0]:>12.1f}{iv[1]:>9.0%}{iv[2]:>9.1f}"
                  f"{hn[0]:>10.1f}{hn[1]:>9.0%}{hn[2]:>9.1f}")

print("\n  recall = of the 5 truly-nearest vectors, how many the index returned.")
print("  An index that is faster but returns the wrong rows is not an optimisation.")
print("""
  TRUST THE SPEED COLUMN. DO NOT TRUST THE RECALL COLUMN.

  Recall here is ID-overlap against exact search, and on this synthetic data that measures
  tie-breaking rather than retrieval quality: ~167 vectors sit around each of 60 centres,
  so hundreds of them are near-equidistant from a query. An index returning a DIFFERENT but
  equally-close five scores zero.

  A second, untested cause is pgvector's default ivfflat.probes = 1: a query searches
  exactly one of `lists` clusters. At 10k rows with lists=10 that is a tenth of the data,
  which predicts roughly the 16% observed.

  Both would need separating before any recall claim is made — by scoring DISTANCE RATIO
  instead of ID overlap, and by sweeping probes / ef_search. Neither was done, because the
  Day 5 decision (no index at 177 rows) does not depend on it. Whoever adds an index must
  do that work first; the speed crossover alone is not sufficient justification.""")
subprocess.run(["dropdb", "--if-exists", DB], check=False)
print(f"  scratch database {DB} dropped")
