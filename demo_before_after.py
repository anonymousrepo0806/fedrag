from __future__ import annotations

import pickle
import time
from unittest import mock

import numpy as np
import requests

import fqp as Q
import sparql_ext as SE
from fedrag_sim import KG

SERVER_A = "http://127.0.0.1:7200/repositories/fair"
SERVER_B = "http://127.0.0.1:7201/repositories/fair"

CONCEPTS = {
    "C_DIAB": "Diabetes Mellitus",
    "C_HTN": "Hypertension",
    "C_OBESITY": "Obesity",
    "C_MI": "Myocardial Infarction",
    "C_STROKE": "Stroke",
    "C_CKD": "Chronic Kidney Disease",
}

EDGES_A = [
    ("C_OBESITY", "risk_factor_for", "C_DIAB"),
    ("C_DIAB", "risk_factor_for", "C_CKD"),
    ("C_DIAB", "risk_factor_for", "C_MI"),
    ("C_MI", "complication_of", "C_CKD"),
]
EDGES_B = [
    ("C_OBESITY", "risk_factor_for", "C_HTN"),
    ("C_HTN", "risk_factor_for", "C_STROKE"),
    ("C_HTN", "risk_factor_for", "C_MI"),
]
EDGES = EDGES_A + EDGES_B

SOURCE_A = {"id": "metabolic-conditions-lod", "fair_score": 0.95, "sparql_endpoint": SERVER_A}
SOURCE_B = {"id": "cardiovascular-risk-lod", "fair_score": 0.89, "sparql_endpoint": SERVER_B}

PATIENT_CODES = ["D_DIAB01", "D_HTN01"]
CODE2CUI = {"D_DIAB01": "C_DIAB", "D_HTN01": "C_HTN"}

N_HOSPITALS = 3


def build_kg_object():
    ents = sorted(CONCEPTS)
    e2i = {e: i for i, e in enumerate(ents)}
    rels = sorted({r for _, r, _ in EDGES})
    r2i = {r: i for i, r in enumerate(rels)}
    triples = np.array([(e2i[h], r2i[r], e2i[t]) for h, r, t in EDGES], dtype=np.int64)

    adj = {}
    for h, _, t in EDGES:
        adj.setdefault(h, set()).add(t)
        adj.setdefault(t, set()).add(h)
    degree = {e: len(adj.get(e, ())) for e in ents}

    kg_dict = {
        "code2cui": CODE2CUI,
        "adj": {k: sorted(v) for k, v in adj.items()},
        "degree": degree,
        "kgc": {"ents": ents, "rels": rels, "triples": triples},
    }
    return KG(kg_dict)


def run_before(kg):
    sources, owners = Q.build_sources(kg.kgc, N_HOSPITALS, repl=2, seed=7)
    summaries = {s: src.bloom for s, src in sources.items()}
    print("Simulated hospitals and what each one's KG partition holds:")
    for s, src in sources.items():
        held_rels = [r for r, ow in owners.items() if s in ow]
        held_rel_names = [kg.kgc["rels"][r] for r in held_rels]
        print(f"  hospital {s}: relations {held_rel_names}, {src.n_triples} triples, "
              f"{len(src.ents)} entities, bloom summary {src.bloom.nbytes} bytes")

    eng = Q.FQPEngine(kg, summaries, Q.local_transport(sources), home=0, decoys=0, hops=2, seed=1)
    t0 = time.perf_counter()
    covs, twos, stats = eng.coverage_batch([PATIENT_CODES])
    elapsed = time.perf_counter() - t0
    cov, two = covs[0], twos[0]
    ranked = Q.rank_from_cov(cov, two, {}, n_docs=1, budget=10)
    comp = Q.completeness(kg, PATIENT_CODES, cov)
    return {"retrieved": ranked, "retrieved_names": [CONCEPTS[c] for c in ranked],
            "stats": stats, "wall_seconds": round(elapsed, 5), "completeness_vs_central_kg": comp}


def seed_fake_servers():
    ns = "http://demo.example.org/"

    def seed(server, edges):
        triples_nt = []
        node_ids = {h for h, _, _ in edges} | {t for _, _, t in edges}
        for cui in node_ids:
            label = CONCEPTS[cui]
            triples_nt.append(f'<{ns}{cui}> <http://www.w3.org/2000/01/rdf-schema#label> "{label}" .')
        for h, r, t in edges:
            triples_nt.append(f"<{ns}{h}> <{ns}{r}> <{ns}{t}> .")
        body = "\n".join(triples_nt)
        resp = requests.post(f"{server}/statements", data=body.encode("utf-8"),
                             headers={"Content-Type": "application/n-triples"}, timeout=10)
        resp.raise_for_status()

    seed(SERVER_A, EDGES_A)
    seed(SERVER_B, EDGES_B)
    print(f"Server A ({SOURCE_A['id']}, FAIR {SOURCE_A['fair_score']}) seeded with {len(EDGES_A)} edges "
          f"(metabolic branch: Obesity->Diabetes->{{CKD,MI}}).")
    print(f"Server B ({SOURCE_B['id']}, FAIR {SOURCE_B['fair_score']}) seeded with {len(EDGES_B)} edges "
          f"(cardiovascular branch: Obesity->Hypertension->{{Stroke,MI}}).")
    print("Note: Hypertension's relations exist ONLY on server B -- server A has no "
          "triples about Hypertension at all.")


def _run_sparql_ext(kg, max_sources, label):
    names_path = "/tmp/demo_names.pkl"
    with open(names_path, "wb") as f:
        pickle.dump(dict(CONCEPTS), f)

    all_sources = [SOURCE_A, SOURCE_B]
    with mock.patch.object(SE, "_pick_endpoints", return_value=all_sources[:max_sources]):
        t_cache0 = time.perf_counter()
        cache = SE.build_cache(names_path, "http://unused", f"/tmp/demo_cache_{max_sources}.pkl",
                               max_sources=max_sources)
        cache_seconds = time.perf_counter() - t_cache0

    print(f"\n{label}")
    print(f"  queried source(s): {[s['id'] for s in cache['source_datasets']]}")
    print(f"  fetched+cached in {round(cache_seconds, 3)}s -- "
          f"{cache['concepts_with_any_match']}/{cache['concepts_queried']} concepts matched a neighbour, "
          f"{cache['concepts_needing_second_source']} of those needed a 2nd source to be found at all")
    for cui in ("C_DIAB", "C_HTN"):
        st = cache["per_concept_stats"][cui]
        print(f"  '{CONCEPTS[cui]}': triples per source {st['triples_fetched_by_source']}, "
              f"answered by {st['answered_by_sources'] or '(none)'}")

    eng = SE.SparqlExtEngine(f"/tmp/demo_cache_{max_sources}.pkl", kg)
    t0 = time.perf_counter()
    covs, twos, stats = eng.coverage_batch([PATIENT_CODES])
    elapsed = time.perf_counter() - t0
    cov, two = covs[0], twos[0]
    ranked = Q.rank_from_cov(cov, two, {}, n_docs=1, budget=10)
    comp = Q.completeness(kg, PATIENT_CODES, cov)
    return {"retrieved": ranked, "retrieved_names": [CONCEPTS[c] for c in ranked],
            "stats": stats, "wall_seconds": round(elapsed, 5), "completeness_vs_central_kg": comp}


def main():
    print("=" * 78)
    print("SCENARIO: a patient's hospital has diagnoses Diabetes + Hypertension on")
    print("record, and wants related-concept context for client-side RAG before predicting")
    print("the patient's next likely diagnoses. The highest-FAIR-score dataset")
    print("(metabolic-conditions-lod) happens to say NOTHING about Hypertension.")
    print("=" * 78)

    kg = build_kg_object()

    print("\n--- BEFORE: fqp arm (query neighbouring simulated FL client hospitals) ---\n")
    before = run_before(kg)

    print("\n--- AFTER: sparql_ext arm (one vs. two FAIR-selected external endpoints) ---")
    seed_fake_servers()
    single = _run_sparql_ext(kg, max_sources=1, label="Step: single top-FAIR source only")
    federated = _run_sparql_ext(kg, max_sources=2, label="Step: federated across top-2 FAIR sources")

    print("\n" + "=" * 78)
    print("SIDE BY SIDE")
    print("=" * 78)
    runs = [("BEFORE (fqp)", before), ("AFTER, 1 source", single), ("AFTER, federated x2", federated)]
    rows = [
        ("Retrieved concepts", lambda r: ", ".join(r["retrieved_names"]) or "(none)"),
        ("Completeness vs. central KG", lambda r: r["completeness_vs_central_kg"]),
        ("Sources contacted / query", lambda r: r["stats"]["sources_contacted_per_query"]),
        ("Live network requests (at query time)", lambda r: r["stats"]["requests"]),
        ("Wall time (this query)", lambda r: f"{r['wall_seconds']}s"),
    ]
    for label, fn in rows:
        print(f"\n{label}")
        for name, r in runs:
            print(f"  {name:<22}: {fn(r)}")

    print("\nWhat this shows: Hypertension's relations exist ONLY on server B, not on")
    print("the single highest-FAIR dataset (server A). Querying server A alone misses")
    print("Stroke entirely -- not because of the 1-hop/label-matching limits discussed")
    print("earlier, but because that data simply isn't in that one dataset. Federating")
    print("the same offline fetch across the top-2 FAIR-qualifying datasets recovers")
    print("it, matching fqp's real-federation behaviour of pulling from whichever")
    print("simulated hospital actually holds the relation -- except here the 'hospitals'")
    print("are real, independently-FAIR-assessed external datasets, queried in parallel")
    print("per concept during the one-time cache build, not on every patient query.")


if __name__ == "__main__":
    main()
