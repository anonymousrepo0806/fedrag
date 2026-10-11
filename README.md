# Federated RAG on MIMIC-III: CPU-only, one machine, Docker or simulation

This repository contains a self-contained experiment layer:

| File | What it is |
|---|---|
| `fedrag_sim.py` | Everything: cohort, KG, retrieval, models, FL methods, KG completion, drug hypotheses, metrics, tables, inference. Runs the **in-process simulation**. |
| `fl_net.py` | The same code split into services that talk over HTTP: `prep`, `server`, `client` (one Docker container each). |
| `fqp.py` | Federated query processing over per-client knowledge graphs. |
| `hypo_learn.py` | Learned, federated ranking of drug hypotheses. |
| `measurements.py` | Laboratory results (LABEVENTS) and vital signs (CHARTEVENTS) as abnormal clinical findings linked to UMLS. |
| `textgen.py`, `textnet.py` | Federated retrieval-augmented **clinical note generation** (simulation / Docker). |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | One small CPU-only image shared by every service. |
| `scripts/*.ps1` | Windows (PowerShell + Docker Desktop). |
| `scripts/*.sh` | Linux / VM. |

The Docker image contains only the `.py` files listed above.

## Components

| Component | Implementation |
|---|---|
| ADE detection (E930–E949) | `TASK=ade` (same-record detection; **E-codes removed from the inputs**, otherwise the label leaks), `TASK=ade_next` (ADE in the next admission) |
| Multitask disease + ADE heads | `TASK=multitask`: mortality_next + ade_next, two heads, all metrics per head, `--ade_weight` |
| Mortality | `TASK=mortality_next` (GraphCare protocol: death in the last admission, from earlier admissions) |
| Each institution's own cases | `data/user_data/client_<i>.csv` (template included); added to that client's **training** data only, never leaves the client |
| Drug hypothesis generation | `HypothesisEngine`: relation-weighted path scoring, run **on each client** for its high-risk test patients, plus an evaluation (see below) |
| EWC + KD | `FL=ewckd`: EWC (Fisher anchored to the received global model) + KD from the global model. |
| FedProx / FedCurv / FedLwF | `FL=fedprox / fedcurv / fedlwf` |
| FedAsync (polynomial staleness) | `FL=fedasync` (simulation: event-driven, heterogeneous client speeds) |
| KG completion (DistMult, MRR/Hits@k) | federated DistMult; `ARM=client_kgc` re-ranks client-side retrieval with it; MRR/Hits@1/Hits@10 logged |
| Agentic RAG over the patient KG + UMLS | retrieval arms `client` (client-side RAG), `server`, `random`, `none`, `server_ctx`, `client_kgc` |
| RETAIN, G-BERT-lite | `MODEL=retain`, `MODEL=transformer` (G-BERT-lite: architecture only, no pre-training), plus `bag` and `sage` |
| Offline local inference | `python fedrag_sim.py infer --model <run>.model.pt --kg work/<task>/kg.pkl --patient patient.json` |
| Resource reporting | per-round resource logging + `docker stats` sampling (CPU, RAM, network, disk per container) |

Text generation is done on MIMIC-III discharge notes with Flan-T5 + LoRA.

### Drug-hypothesis engine details
1. **It could never reach drugs that treat a condition.** UMLS stores `may_treat` as *drug → condition*, but a forward search from the patient's condition cannot reach them. The search therefore also walks treatment, ingredient, hierarchy and drug-family links in reverse (`~may_treat` = "is treated by").
2. **It could propose contraindicated drugs.** The search followed `may_contraindicate` edges to reach candidates; for a patient with renal failure, it "proposed" doxycycline because it is contraindicated in renal failure. Safety relations are now never used to reach candidates. Contraindications are checked against the patient's **conditions and** current drugs, and contraindicated drugs are removed (`removed_contraindicated` counts them). Drugs that interact with current medications are kept but flagged and penalised.

### Learned, federated hypothesis ranking (`hypo_learn.py`, on by default)
The KG search only **generates candidates**, with their evidence paths. **Ranking is learned** from real outcomes:

- **Labels (no manual annotation):** for each training patient, a candidate drug is positive if it was actually prescribed at the next admission.
- **Hybrid candidate set:** the KG candidates plus the client's 20 most-prescribed drugs (`--hyp_pop_cands`). The popular drugs have no KG evidence. Without them, the next-admission drug is often not among the KG candidates at all, which caps any ranker.
- **26 features per (patient, drug):**
  - the rule score, the number and length of evidence paths, and from how many of the patient's conditions the drug is reached
  - counts per relation type (treats, ingredient, risk factor, …)
  - interactions with current drugs and the drug's local popularity
  - the patient's predicted risk
  - the federated KG-completion plausibility of (drug, may_treat, condition), when trained (`--kgc_rounds`)
- **Federated training:**
  - Feature standardisation from federated sums (counts, sums, sums of squares; no data).
  - Then FedAvg rounds (`--hyp_rounds 20`) of a **linear** ranker (`--hyp_model mlp` for a small MLP).
  - In Docker, each client trains on its own patients and only ranker weights travel.
- **Interpretable:** the summary lists the learned linear weights, i.e. which kinds of evidence actually predict prescriptions.
- **Evaluation on the high-risk test patients** (P@5, Hit@5, nDCG@5, MRR) of:
  - **learned ranker**
  - **rule ranking** (hand-set weights)
  - **popularity baseline**

  Also reported: **KG candidate recall** and **hybrid candidate recall** (how often the prescribed drug is among the candidates at all), and the learned weights.
- `--hyp_learn 0` keeps the rule-based ranking only.

**Evaluation of hypotheses:** for next-admission tasks, the hypothesised drugs are compared with the drugs actually prescribed at the next admission (P@5, Hit@5). This is reported next to a **popularity baseline**: the most common next-admission drugs in that client's training data. Expect low absolute numbers. Hypotheses are candidate therapies, not predictions of what was prescribed, and drug-name→UMLS matching is approximate. Report them as an exploratory output.

## Getting MIMIC-III fast: BigQuery instead of the PhysioNet download
Downloading from PhysioNet can take hours. MIMIC-III is also on Google BigQuery, with the same credentials. The queries in `scripts/bigquery/` fetch only what the pipeline reads, about 0.8 GB in total instead of about 7 GB.

1. **Link your Google account.** On physionet.org, open your profile → **Settings → Cloud** and add your Google account email.
2. **Request access.** On the MIMIC-III Clinical Database page, under *Files*, click **"Request access using Google BigQuery"**.
3. **Open BigQuery.** Go to https://console.cloud.google.com/bigquery and create a project. The free "sandbox" works: no billing, and 1 TB of queries per month is free.
4. **Run each query and save the result.** For every `.sql` file in `scripts/bigquery/`: paste it, click **Run**, then **Save results → CSV (Google Drive)**. Download the CSV from Drive into `data\mimic3` and rename it to the name of the query:

| Query → file | Size | Needed for |
|---|---|---|
| `ADMISSIONS`, `DIAGNOSES_ICD`, `PROCEDURES_ICD`, `PRESCRIPTIONS` | ~150 MB | everything |
| `NOTEEVENTS` (discharge summaries only) | ~0.6 GB | note generation |
| `LAB_FINDINGS` | a few MB | lab findings, computed in BigQuery (replaces LABEVENTS) |
| `VITAL_FINDINGS` | a few MB | vital-sign findings, computed in BigQuery (replaces the 4 GB CHARTEVENTS) |
| `D_LABITEMS` | tiny | optional check of the lab item IDs |

`LAB_FINDINGS.sql` and `VITAL_FINDINGS.sql` are generated from `measurements.py` (`sql_labs()`, `sql_vitals()`), so they apply exactly the same rules as the Python code. On test data the two give identical results. BigQuery uses an approximate median for the lab reference values, which can shift borderline cases very slightly on real data. Column names and date formats from BigQuery are handled automatically.

## Laboratory results and vital signs (`measurements.py`, on by default)
**Which MIMIC-III tables are needed:**
- **Codes and notes:** ADMISSIONS, DIAGNOSES_ICD, PROCEDURES_ICD, PRESCRIPTIONS, NOTEEVENTS.
- **Measurements:** LABEVENTS, CHARTEVENTS and D_LABITEMS (used only to check the lab item IDs).

```bash
for t in ADMISSIONS DIAGNOSES_ICD PROCEDURES_ICD PRESCRIPTIONS NOTEEVENTS LABEVENTS CHARTEVENTS D_LABITEMS; do
  wget -N -c --user <physionet-user> --ask-password https://physionet.org/files/mimiciii/1.4/$t.csv.gz
done
```

**What it does.** Abnormal readings during a stay become **clinical findings**: concepts such as *hyperkalemia*, *anemia* or *hypoxemia* that also exist in UMLS.
- **Labs.** 24 common blood tests (potassium, sodium, glucose, haemoglobin, WBC, platelets, creatinine, urea, lactate, bilirubin, INR, pH, bicarbonate, albumin, Ca, Mg, phosphate, chloride, AST, ALT, troponin T, uric acid, pCO2, pO2). They use MIMIC's own `FLAG = abnormal`. Each abnormal result is called high or low relative to the median of that test's normal results, so units do not matter.
- **Vitals.** Heart rate, systolic BP, respiratory rate, SpO2 and temperature, from both MIMIC systems (CareVue and MetaVision item IDs; °F converted). They use standard adult thresholds: HR >100 / <60, SBP >160 / <90, RR >24, SpO2 <92 %, T >38 / <36 °C. Readings outside plausible ranges are dropped.
- **When a finding is recorded.** A stay gets a finding only when at least 30 % of that measurement's readings are abnormal in that direction (`MEAS_FRAC`). A single outlier does not count.
- **Tokens and KG links.** Findings enter each visit as `L_<finding>` and `V_<finding>`, next to the diagnosis, procedure and drug codes. 42 of the 43 findings are linked to a UMLS concept that has edges in the GraphCare KG. Raised troponin is kept as a model feature only, because no faithful concept exists.

**Where the findings are used:**
1. **Patient graph and models:** as extra nodes, in all four models.
2. **Retrieval:** as extra entry points into the KG for every retrieval arm, including FQP.
3. **Drug hypotheses:** as conditions. For example, *low blood pressure → vasopressin* and *hyperkalemia → drugs that may_treat it*. Contraindications linked to findings are now removed too.
4. **Note generation:** in the prompt, as "Abnormal laboratory results: …" and "Abnormal vital signs: …".
5. **Each hospital's local cases:** in the `labs` and `vitals` columns of `client_<i>.csv`.

**Cost.** One streamed pass over the tables, in chunks of 1M rows. It takes about 10–20 min for CHARTEVENTS's 330M rows and stays under 1 GB RAM on CPU. The result is cached in `work\measurements.pkl` and shared by all tasks. Keep that file when you clear `work\`. If LABEVENTS or CHARTEVENTS is missing, that part is skipped with a message, and everything else still runs.

**Ablation.** `MEAS=0` (`-Meas 0`, `--meas 0`) runs the same patients with codes only. The run names get `_nomeas`, and the tables show "(codes only, no labs/vitals)". `docker_sweep` and `sweep --grid all` already include the no-findings runs for No RAG, server, client and FQP.

**Leakage note.** For the `*_next` tasks, findings come only from *earlier* admissions, as all inputs do. For `ade` and note generation, they come from the same stay, which is information available before discharge.

## Federated query processing (`ARM=fqp`)

The system includes a query analyser, decomposition and a federated execution planner:

- **Each client holds its own KG.** The UMLS graph around the cohort is split by relation type, and each relation is held by `FQP_REPL` clients (default 2). The clients' KGs therefore differ and overlap only partly. In Docker, each client container builds and keeps **only its own partition**.
- **Source selection.** Each client publishes a Bloom-filter summary of the entities in its KG. Summaries contain no triples and no patients. The server only keeps the directory of summaries and addresses; it never sees queries.
- **The query engine is the patient's own client.** It decomposes the patient query (the patient's concepts) into one sub-query per source, holding only the entities that source can answer. Sub-queries are sent **directly to the other client containers** (HTTP, port 8090). Each source answers from its own KG, and the answers are merged.
- **Bound join (`FQP_HOPS=2`).** The best first-hop candidates are sent as a second, bound sub-query (as in FedX), so paths that cross two hospitals' KGs are found. The join evidence is used in ranking.
- **Decoys (`FQP_DECOYS=k`).** Each remote sub-query is padded with k random entities, so a source cannot tell which concepts are really being asked about. The extra cost is measured.
- **Baselines:**
  - `client_local`: the same client, but only its own KG (no federation).
  - `server`: one central KG at the server.
  - `client`: every client holds a full copy of the KG.

**Measured per patient query:** sources contacted, sub-queries, join sub-queries, wasted contacts (a summary said yes but the source had nothing), KB sent and received, ms per query, summary size, and **completeness**: the share of the candidates the central KG would give that the federation found. The completeness check uses the central KG for evaluation only.

FQP works with every FL method and model. In Docker: `-Arm fqp` (PowerShell) or `ARM=fqp` (bash).

Note that every hospital KG covers the common concepts, so entity-level source selection mostly shrinks each sub-query rather than skipping whole sources. Report this as it comes out.

## Clinical note generation (`TASK=notes_diagnosis` / `notes_course`)

The system also generates text, on MIMIC-III:

- **Target:** the *Discharge Diagnosis* section (default), or the *Brief Hospital Course* section, of each admission's real discharge summary (`NOTEEVENTS`, category "Discharge summary"). De-identification brackets are removed.
- **Input:**
  - The admission's coded record, written out as text: ICD-9 diagnosis and procedure names (from `GraphCare-main/resources`) and drug names.
  - The **KG context retrieved by the arm**: none, random, server, client, client_local, **fqp** (federated query processing), client_kgc or server_ctx.
- **`--hide_dx 1` / `-HideDx 1`** removes the diagnosis codes from both the input and the retrieval query. The model then has to infer the diagnoses from procedures, drugs and retrieved knowledge, so retrieval and FQP really matter. Run both settings: the run scripts do this by default.
- **Generator:** `google/flan-t5-small` with **LoRA** (rank 8, about 0.3 M trainable parameters).
  - Federated with FedAvg, FedProx, local-only or centralised training.
  - Only the LoRA weights are exchanged, about 1 MB per client per round.
  - It runs on a CPU. `--lora_r 0` switches to full fine-tuning.
- **Metrics** (offline, no external LLM judge):
  - ROUGE-1, ROUGE-2, ROUGE-L and BLEU.
  - Optional BERTScore (`--bertscore`; downloads a RoBERTa model).
  - UMLS **concept-level** metrics, matched against a 300k-name UMLS dictionary:
    - **Concept precision / recall / F1:** generated against reference concepts.
    - **Faithfulness:** the share of generated concepts that are supported by the input context.
    - **Hallucination:** the share of generated concepts found in neither the context nor the reference.
    - **Context recall:** the share of reference concepts that the input context contains, which measures retrieval quality for generation.

  These are deterministic versions of the Ragas metrics. The matcher has one name per concept (no synonyms), so absolute concept scores are conservative.
- **Model selection:** best validation ROUGE-L. The test is run with those adapters; test data is never used for selection.
- **Outputs:**
  - `*.summary.json`
  - `*.examples.json`: generated against reference notes. These contain MIMIC text, so never publish them.
  - `tables.tex` and `all_text_runs.csv`
- **CPU budget per client:** `--tg_max_train 400`, `--tg_max_val 30` and `--tg_max_test 100` items. Raise them if you have time.

Run (simulation in the Docker image; needs `NOTEEVENTS.csv` or `.csv.gz` in `data\mimic3`):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_text.ps1 -Seeds 1 -Rounds 2 -MaxTrain 50
powershell -ExecutionPolicy Bypass -File scripts\run_text.ps1 -ClientCounts 10 -Seeds 1,2,3
```
Distributed (one container per client, FQP between clients; use fewer clients and `CLIENT_MEM=1600m`):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\docker_run.ps1 -Task notes_diagnosis -Arm fqp -Clients 4 -HideDx 1
```

### Each hospital's own local cases (`data\user_data\client_<i>.csv`)
These can be real local data, if a site has any. Otherwise they can be **simulated from MIMIC**:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\make_user_data.ps1 -Clients 10 -Fraction 0.10
Get-ChildItem work -Exclude measurements.pkl,measurements.stats.json,hf | Remove-Item -Recurse
```
This holds back 10% of MIMIC patients from the shared cohort and splits them across the clients as their private cases. It also writes `reserved_subjects.txt`, so `build`/`prep` leave them out of the shared cohort and no patient appears twice. Each client adds its own file to its **training** data only. This is *simulated* institution-specific data drawn from held-out MIMIC patients. These local cases are also assigned non-IID (specialty-skewed Dirichlet shares; `--partition random` gives round-robin).

## How MIMIC is distributed across the 10 clients (non-IID by default)
You only put the MIMIC tables in `data\mimic3`. `prep` (Docker) or `train` (simulation) splits the patients across the clients automatically. Every arm, FL method and model gets **the same split** for a given seed, so comparisons stay fair.

`PARTITION=noniid` (default) simulates hospitals with different specialties and case mixes:
- **Feature/specialty skew:** each patient's dominant ICD-9 chapter (circulatory, respiratory, neoplasms, injury, ...) is the "specialty" of the case.
- **Label skew:** the label (mortality / ADE) is combined with the specialty to make the group.
- **Quantity skew:** each group is split across hospitals in Dirichlet(`ALPHA`) shares. The default `ALPHA` is 0.5; a smaller value makes the split more skewed.
- **Size floor:** each client keeps at least about 2% of the patients, so every hospital has usable train/val/test splits. Splits within a client are stratified.

| Partition | Description | Mean JS divergence of specialty mix vs global* | Label-rate std across clients* | Size CV* |
|---|---|---|---|---|
| `noniid` (default) | specialty + label + size skew | 0.098 | 0.07 / 0.14 | 0.39 |
| `random` | random sizes, mixed content | 0.033 | 0.02 / 0.03 | 0.53 |
| `iid` | equal, stratified | 0.027 | 0.02 / 0.02 | 0.00 |

\*Values are from the synthetic test cohort. Real MIMIC has a more uneven specialty mix, so its skew will be larger. The real values are written to `work\<task>\c10__noniid__seed<s>\partition_stats.json` and to each run's `summary.json` (`partition_stats`). That file holds per-client size, label rates and chapter mix.

To change the partition: `-Partition iid|random|dirichlet` on `docker_run.ps1`, or `PARTITION=` in `.env`. Changing it creates a new split folder and new run tags (`__noniid__` vs `__iid__`), so the results do not overwrite each other.

## Run on Windows (Docker Desktop)

1. Put the four MIMIC-III tables in `data\mimic3\`: ADMISSIONS, DIAGNOSES_ICD, PROCEDURES_ICD, PRESCRIPTIONS (`.csv` or `.csv.gz`). The KG files are already in `GraphCare-main\`.
2. Copy `.env.example` to `.env` and check it. The defaults point to those folders; edit only if your MIMIC folder is elsewhere.
3. Run one distributed experiment (prep, server and 10 client containers):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\docker_run.ps1 -Task multitask -Fl ewckd -Arm client -Clients 10
   powershell -ExecutionPolicy Bypass -File scripts\docker_run.ps1 -Task multitask -Arm fqp -Clients 10
   powershell -ExecutionPolicy Bypass -File scripts\docker_run.ps1 -Task multitask -Arm fqp -Clients 10 -FqpHops 1 -FqpDecoys 5
   ```
4. All distributed runs (FedAvg/FedProx/FedCurv/FedLwF/EWC+KD × none/server/client, plus models), then tables:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\docker_sweep.ps1 -Task multitask -Seeds 1,2,3 -ClientCounts 10
   ```
5. The full simulation runs inside the same image, with every arm and baseline, including the ones that are not distributed (client_kgc, server_ctx, FedAsync, local, central):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\run_sim.ps1 -Task multitask -ClientCounts 10 -Seeds 1,2,3
   ```
   **This is the fastest way to get all paper numbers.**

Results: `results\` (Docker runs) and `results\sim_<task>\` (simulation). Each folder gets `tables.tex` and `all_runs.csv`.
Run `scripts\make_tables.ps1` to rebuild the tables at any time.

Give Docker Desktop at least 8 GB of memory for 10 client containers (Settings → Resources).

## Run on Linux / the VM
```bash
TASK=multitask CLIENT_COUNTS=10 bash scripts/run_sim.sh ./data/mimic3 ./GraphCare-main/KG_mapping
TASK=multitask FL=ewckd ARM=client CLIENTS=10 bash scripts/docker_run.sh
```

## What is recorded
**Per round**, per head:
- AUROC, AUPRC, F1 (threshold chosen on **validation**), F1@0.5, precision, recall, specificity, NPV, accuracy, balanced accuracy, MCC, Brier, log-loss, ECE, confusion matrix
- per-client metrics, plus worst-client and std of AUROC
- train loss, wall/CPU time, RAM and peak RAM, Fisher time
- bytes up/down, async staleness

**Per run:**
- the selected round: best mean validation AUPRC. Test data is never used for selection.
- retrieval time, graph statistics, parameter count, MB communicated, inference ms/patient
- KG-completion MRR/Hits@k
- drug-hypothesis statistics, and example hypotheses with names and evidence paths (`*.hypotheses_examples.json`)

**Retrieval:** masked-diagnosis evaluation (P@k, R@k, nDCG@k, Cov@k, Hit@k, MRR, latency).

**Docker:** `*.docker_stats.csv` (CPU %, RAM, network and disk per container every 5 s) and `*.containers.log`.

## Notes
- The EWC strength matters: try `-LamEwc`/`--lam_ewc` 0.5, 1, 10. With the Fisher computed here, small λ has almost no effect.
- `work\` and `data\` contain MIMIC-derived data. Never upload them; `.gitignore` keeps them out of the repo and `.dockerignore` keeps them out of the image.
- The KG files are UMLS-derived; check that your UMLS licence covers any redistribution.
