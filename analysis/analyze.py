import json, glob, os, statistics as st
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__))
SW = os.environ.get("SWEEP", "sweep_main_v2")
RET_PATH = os.environ.get("RET_ROWS", os.path.join(HERE, "retrieval_rows.json"))
ORDER = ["none","random","server","server_ctx","client","client_nolink","client_sub","client_kgc","client_local","fqp"]
NAME = {"client_nolink":"Client-side RAG, no graph links","client_sub":"Client-side RAG, neighbour subgraph","none":"FedAvg w/o RAG","random":"FedAvg + random context","server":"FedAvg + central RAG",
        "server_ctx":"FedAvg + central RAG w/ context","client":"FedAvg + client-side RAG",
        "client_kgc":"Client-side RAG + KGC","client_local":"Client-side RAG, own KG only","fqp":"FedAvg + FQP RAG"}
TN = {"client_nolink":"RAG, no links","client_sub":"RAG, subgraph","none":"No RAG","random":"Random context","server":"Central RAG","server_ctx":"Central RAG+ctx","client":"Client RAG","client_kgc":"Client RAG+KGC","client_local":"Own KG only","fqp":"FQP RAG"}
SHORT = {"client_nolink":"No links","client_sub":"Subgraph","none":"No RAG","random":"Random","server":"Central","server_ctx":"Central+ctx","client":"Client RAG",
         "client_kgc":"Client RAG+KGC","client_local":"Own KG","fqp":"FQP"}
COL = {"client_nolink":"#8C564B","client_sub":"#7F7F00","none":"#222222","random":"#999999","server":"#E69F00","server_ctx":"#D55E00","client":"#0072B2",
       "client_kgc":"#56B4E9","client_local":"#009E73","fqp":"#CC79A7"}
LS = {"client_nolink":"--","client_sub":"-.","none":"-","random":"--","server":"-.","server_ctx":":","client":"-","client_kgc":"--","client_local":"-.","fqp":"-"}
D, R = {}, {}
for f in sorted(glob.glob(SW + "/*.summary.json")):
    d = json.load(open(f)); a, s = d["arm"], d["seed"]
    D.setdefault(a, {})[s] = d
    R.setdefault(a, {})[s] = [json.loads(l) for l in open(f.replace(".summary.json", ".jsonl"))]
ORDER = [a for a in ORDER if a in D]
seeds = sorted(D["none"])
HEAD = list(D["none"][seeds[0]]["final_heads"])[0]
HAVE_RET = os.path.exists(RET_PATH) and not os.environ.get("NO_RET")
OUT = os.environ.get("OUT", "analysis/out")
os.makedirs(OUT, exist_ok=True)
def ms(vals):
    v = np.array(vals, float)
    return float(v.mean()), float(v.std(ddof=1)) if len(v) > 1 else 0.0
def agg(fn):
    return {a: ms([fn(D[a][s]) for s in seeds]) for a in ORDER}
def fmt(m, sd, p=3):
    return f"{m:.{p}f}$\\pm${sd:.{p}f}"
def bold_best(cells, higher=True, p=3):
    vals = [c[0] for c in cells]
    b = max(vals) if higher else min(vals)
    out = []
    for m, sd in cells:
        t = fmt(m, sd, p)
        out.append("\\textbf{" + f"{m:.{p}f}" + "}$\\pm$" + f"{sd:.{p}f}" if abs(m - b) < 10 ** (-p) / 2 else t)
    return out
fh = lambda d, k: d["final_heads"][HEAD]["test"][k]
ML = [("AUROC","auroc",True),("AUPRC","auprc",True),("F1","f1",True),("Prec.","precision",True),("Rec.","recall",True),
      ("Spec.","specificity",True),("BAcc","balanced_accuracy",True),("MCC","mcc",True),("Brier","brier",False),
      ("ECE","ece",False),("LogL","logloss",False)]
ml = {k: agg(lambda d, k=k: fh(d, k)) for _, k, _ in ML}
wc = agg(lambda d: d["final_heads"][HEAD]["worst_client_auroc"])
sc = agg(lambda d: d["final_heads"][HEAD]["std_client_auroc"])
rows = []
for part, items in (("a", ML[:6]), ("b", ML[6:])):
    pass
def mltable(items, extra, cap, lab):
    cols = "l" + "c" * (len(items) + len(extra))
    h = " & ".join([n for n, _, _ in items] + [e[0] for e in extra])
    body = []
    cells = {n: bold_best([ml[k][a] for a in ORDER], hi) for n, k, hi in items}
    for e in extra:
        cells[e[0]] = bold_best([e[1][a] for a in ORDER], e[2])
    for i, a in enumerate(ORDER):
        body.append(TN[a] + " & " + " & ".join(cells[c][i] for c in [n for n, _, _ in items] + [e[0] for e in extra]) + " \\\\")
    return ("\\begin{table}[t]\n\\centering\n\\caption{" + cap + "}\n\\label{" + lab + "}\n\\scriptsize\\setlength{\\tabcolsep}{2.2pt}\n"
            "\\begin{tabular}{@{}" + cols + "@{}}\n\\toprule\nArchitecture & " + h + " \\\\\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")
t_ml1 = mltable(ML[:7], [], f"Final-round (round 20) test metrics, mean$\\pm$sd over {len(seeds)} seeds. Threshold-dependent metrics use the validation-optimal F1 threshold.", "tab:ml1")
t_ml2 = mltable(ML[7:], [("Worst-client AUROC", wc, True), ("Client-AUROC sd", sc, False)],
                f"Final-round calibration, MCC and per-client fairness (mean$\\pm$sd over {len(seeds)} seeds).", "tab:ml2")
ed = {k: agg(lambda d, k=k: d["resources"][k] if not isinstance(d["resources"][k], dict) else 0) for k in ("total_mb_up", "total_mb_down", "mean_round_wall_s", "infer_ms_per_patient")}
tot = agg(lambda d: d["resources"]["total"]["wall_s"])
ret = agg(lambda d: d["resources"]["retrieval_and_graphs"]["wall_s"])
ltr = agg(lambda d: d["efficiency"]["total_local_train_secs_all_clients"])
ttc = agg(lambda d: d["efficiency"]["time_to_convergence_s"])
cvr = agg(lambda d: d["efficiency"]["convergence_round"])
pk = agg(lambda d: d["resources"]["total"]["peak_rss_mb"])
nd = agg(lambda d: d["graph_stats"]["mean_nodes"])
eg = agg(lambda d: d["graph_stats"]["mean_edges"])
def fq(a, k, scale=1.0):
    vals = [D[a][s]["fqp"][k] * scale for s in seeds if D[a][s].get("fqp")]
    return ms(vals) if vals else None
cost_rows = []
for a in ORDER:
    f = fq(a, "total_mb")
    cost_rows.append(" & ".join([TN[a], f"{tot[a][0]:.0f}", f"{ret[a][0]:.1f}", f"{ltr[a][0]:.0f}", f"{ed['mean_round_wall_s'][a][0]:.1f}",
        f"{ttc[a][0]:.0f}", f"{ed['total_mb_up'][a][0]:.0f}", f"{ed['total_mb_down'][a][0]:.0f}", f"{f[0]:.0f}" if f else "--",
        f"{pk[a][0]:.0f}", f"{nd[a][0]:.1f}"]) + " \\\\")
t_cost = ("\\begin{table}[t]\n\\centering\n\\caption{Time and communication per run (mean over " + str(len(seeds)) + " seeds): total wall time, retrieval and graph building time, summed client training time, mean time per round, time to convergence (s); model uplink/downlink and retrieval traffic (MB); peak memory (MB); nodes per patient graph.}\n\\label{tab:cost}\n"
          "\\scriptsize\\setlength{\\tabcolsep}{2pt}\n\\begin{tabular}{@{}lcccccccccc@{}}\n\\toprule\nArchitecture & Wall & Retr. & Train & s/rnd & Conv. & Up & Down & Retr. MB & Peak & Nodes \\\\\n\\midrule\n"
          + "\n".join(cost_rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")
RET = json.load(open(RET_PATH)) if HAVE_RET else []
RA = ["random","server","server_ctx","client","client_kgc","client_local","fqp"]
rm = {a: {} for a in RA}
for a in (RA if HAVE_RET else []):
    rr = [r for r in RET if r["arm"] == a]
    for k in rr[0]:
        if k in ("clients", "seed", "arm"): continue
        rm[a][k] = ms([r[k] for r in rr])
RK = [("MRR","MRR"),("P@5","P@5"),("P@10","P@10"),("P@20","P@20"),("R@10","R@10"),("R@20","R@20"),("nDCG@5","nDCG@5"),("nDCG@10","nDCG@10"),("nDCG@20","nDCG@20"),("Cov@10","Cov@10"),("Hit@5","Hit@5"),("Hit@10","Hit@10"),("Hit@20","Hit@20")]
def rtable(keys, cap, lab, extra_lat=False):
    cells = {k: bold_best([rm[a][k] for a in RA], True) for _, k in keys}
    body = []
    for i, a in enumerate(RA):
        body.append(TN[a] + " & " + " & ".join(cells[k][i] for _, k in keys) + (f" & {rm[a]['latency_ms_per_query'][0]:.1f}" if extra_lat else "") + " \\\\")
    return ("\\begin{table}[t]\n\\centering\n\\caption{" + cap + "}\n\\label{" + lab + "}\n\\scriptsize\\setlength{\\tabcolsep}{2.4pt}\n\\begin{tabular}{@{}l" + "c" * (len(keys) + int(extra_lat)) + "@{}}\n\\toprule\nRetriever & "
            + " & ".join(n for n, _ in keys) + (" & ms/q" if extra_lat else "") + " \\\\\n\\midrule\n" + "\n".join(body) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")
t_r1 = "" if not HAVE_RET else rtable([("MRR","MRR"),("P@5","P@5"),("P@10","P@10"),("P@20","P@20"),("R@10","R@10"),("R@20","R@20")], "Retrieval metrics on the masked-diagnosis task, mean$\\pm$sd over 3 seeds (about 1,490 queries per seed).", "tab:ret1")
t_r2 = "" if not HAVE_RET else rtable([("nDCG@5","nDCG@5"),("nDCG@10","nDCG@10"),("nDCG@20","nDCG@20"),("Cov@10","Cov@10"),("Hit@5","Hit@5"),("Hit@10","Hit@10"),("Hit@20","Hit@20")], "Ranking quality, coverage and hit rate of the retrievers, with latency per query.", "tab:ret2", True)
fqrows = []
for k, lab, sc_ in (("completeness_vs_central_kg","Completeness vs.\\ central KG",1),("sources_contacted_per_query","Sources contacted / query",1),
                    ("remote_sources_per_query","Remote sources / query",1),("subqueries_per_query","Sub-queries / query",1),
                    ("remote_subqueries_per_query","Remote sub-queries / query",1),("join_subqueries_per_query","Bound-join sub-queries / query",1),
                    ("wasted_contacts_per_query","Wasted contacts / query",1),("req_bytes_per_query","Request bytes / query",1),
                    ("resp_bytes_per_query","Response bytes / query",1),("ms_per_query","Engine ms / query",1),("total_mb","Retrieval traffic per run (MB)",1),
                    ("summary_bytes","Published summaries (bytes)",1)):
    cs = []
    for a in ("client_local", "fqp"):
        v = ms([D[a][s]["fqp"][k] for s in seeds])
        cs.append(f"{v[0]:.3f}$\\pm${v[1]:.3f}" if v[0] < 100 else f"{v[0]:,.0f}$\\pm${v[1]:,.0f}".replace(",", "\\,"))
    fqrows.append(f"{lab} & {cs[0]} & {cs[1]} \\\\")
t_fqp = ("\\begin{table}[t]\n\\centering\n\\caption{Federated query processing statistics per query (mean$\\pm$sd over " + str(len(seeds)) + " seeds): own KG only versus FQP over ten relation-partitioned sources.}\n\\label{tab:fqp}\n\\small\\setlength{\\tabcolsep}{4pt}\n\\begin{tabular}{@{}lcc@{}}\n\\toprule\n & Own KG only & FQP \\\\\n\\midrule\n"
         + "\n".join(fqrows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}\n")
for n, t in (("ml1", t_ml1), ("ml2", t_ml2), ("cost", t_cost)) + ((("ret1", t_r1), ("ret2", t_r2)) if HAVE_RET else ()) + ((("fqp", t_fqp),) if "fqp" in D else ()):
    t = t.replace("\\begin{tabular}", "\\resizebox{\\linewidth}{!}{\\begin{tabular}").replace("\\end{tabular}", "\\end{tabular}}")
    open(f"{OUT}/tab_{n}.tex", "w").write(t)
plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25, "pdf.fonttype": 42, "figure.dpi": 150})
def rounds_curve(a, fn):
    arr = np.array([[fn(r) for r in R[a][s]] for s in seeds], float)
    return arr.mean(0), arr.std(0, ddof=1)
x = np.arange(1, 21)
fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.5))
for a in ORDER:
    for axi, fn, yl in ((ax[0], lambda r: r["heads"][HEAD]["test"]["auroc"], "Test AUROC"),
                         (ax[1], lambda r: r["heads"][HEAD]["test"]["auprc"], "Test AUPRC"),
                         (ax[2], lambda r: r["train_loss"], "Train loss")):
        m, sd = rounds_curve(a, fn)
        axi.plot(x, m, ls=LS[a], color=COL[a], lw=1.2, label=SHORT[a])
        axi.set_xlabel("Round"); axi.set_ylabel(yl)
ax[0].set_ylim(0.52, 0.66)
h, l = ax[0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=8, frameon=False, fontsize=7, handlelength=2.2, columnspacing=1)
fig.tight_layout(rect=(0, .1, 1, 1)); fig.savefig(f"{OUT}/fig_rounds.pdf"); plt.close(fig)
fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.5))
w = np.arange(len(ORDER))
ax[0].bar(w, [ret[a][0] for a in ORDER], color="#D55E00", label="Retrieval + graph build")
ax[0].bar(w, [tot[a][0] - ret[a][0] for a in ORDER], bottom=[ret[a][0] for a in ORDER], color="#0072B2", label="Training + aggregation + eval")
ax[0].set_ylabel("Seconds per run"); ax[0].set_title("Wall time\n\n\n", fontsize=8)
ax[0].set_xticks(w); ax[0].set_xticklabels([SHORT[a] for a in ORDER], rotation=60, ha="right"); ax[0].legend(frameon=False, fontsize=6, loc="lower center", bbox_to_anchor=(.5, 1.12))
up = [ed["total_mb_up"][a][0] / 1000 for a in ORDER]; dn = [ed["total_mb_down"][a][0] / 1000 for a in ORDER]
rt = [(fq(a, "total_mb")[0] / 1000 if fq(a, "total_mb") else 0) for a in ORDER]
ax[1].bar(w, up, color="#009E73", label="Model uplink"); ax[1].bar(w, dn, bottom=up, color="#56B4E9", label="Model downlink")
ax[1].bar(w, rt, bottom=[u + d for u, d in zip(up, dn)], color="#CC79A7", label="Retrieval traffic")
ax[1].set_ylabel("GB per run"); ax[1].set_title("Communication\n\n\n\n", fontsize=8)
ax[1].set_xticks(w); ax[1].set_xticklabels([SHORT[a] for a in ORDER], rotation=60, ha="right"); ax[1].legend(frameon=False, fontsize=6, loc="lower center", bbox_to_anchor=(.5, 1.12), ncol=1)
for a in ORDER:
    cw = np.array([[c for c in D[a][s]["efficiency"]["cumulative_wall_s_by_round"]] for s in seeds]).mean(0)
    ax[2].plot(x, cw, ls=LS[a], color=COL[a], lw=1.2, label=SHORT[a])
ax[2].set_xlabel("Round"); ax[2].set_ylabel("Cumulative wall s"); ax[2].set_title("Wall time vs round", fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_cost.pdf", bbox_inches="tight"); plt.close(fig)
if HAVE_RET:
    fig, ax = plt.subplots(1, 4, figsize=(7.6, 2.3))
    for axi, k in zip(ax, ("MRR", "P@10", "nDCG@10", "Hit@10")):
        m = [rm[a][k][0] for a in RA]; e = [rm[a][k][1] for a in RA]
        axi.bar(range(len(RA)), m, yerr=e, color=[COL[a] for a in RA], capsize=1.5, error_kw={"lw": .7})
        axi.set_title(k, fontsize=8); axi.set_xticks(range(len(RA))); axi.set_xticklabels([SHORT[a] for a in RA], rotation=60, ha="right")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_retrieval.pdf"); plt.close(fig)
OFF0 = {"server_ctx": (-30, 6), "client": (-24, -10), "client_kgc": (6, 10), "fqp": (6, -12), "server": (-30, -10)}
OFF1 = {"random": (-6, -14), "client": (-8, -14), "server": (-14, 8), "server_ctx": (4, 8), "client_local": (-28, 6), "none": (4, 10)}
fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.7))
fin = agg(lambda d: d["final_test"]["auroc"])
if HAVE_RET:
    for a in RA:
        ax[0].errorbar(rm[a]["P@10"][0], fin[a][0], yerr=fin[a][1], xerr=rm[a]["P@10"][1], fmt="o", color=COL[a], ms=5, capsize=2, lw=.7)
        ax[0].annotate(SHORT[a], (rm[a]["P@10"][0], fin[a][0]), textcoords="offset points", xytext=OFF0.get(a, (4, 4)), fontsize=6.5)
    ax[0].errorbar(0, fin["none"][0], yerr=fin["none"][1], fmt="s", color=COL["none"], ms=5, capsize=2, lw=.7)
    ax[0].annotate("No RAG", (0, fin["none"][0]), textcoords="offset points", xytext=(4, 4), fontsize=6.5)
    ax[0].set_xlabel("Retrieval P@10"); ax[0].set_ylabel("Final test AUROC"); ax[0].set_title("Retrieval quality vs prediction", fontsize=8)
else:
    for a in ORDER:
        ax[0].errorbar(nd[a][0], fin[a][0], yerr=fin[a][1], fmt="o", color=COL[a], ms=5, capsize=2, lw=.7)
        ax[0].annotate(SHORT[a], (nd[a][0], fin[a][0]), textcoords="offset points", xytext=(4, 4), fontsize=6.5)
    ax[0].set_xlabel("Nodes per patient graph"); ax[0].set_ylabel("Final test AUROC"); ax[0].set_title("Graph size vs prediction", fontsize=8)
for a in ORDER:
    ax[1].errorbar(tot[a][0], fin[a][0], yerr=fin[a][1], fmt="o", color=COL[a], ms=5, capsize=2, lw=.7)
    ax[1].annotate(SHORT[a], (tot[a][0], fin[a][0]), textcoords="offset points", xytext=OFF1.get(a, (4, 4)), fontsize=6.5)
ax[1].set_xlabel("Wall time per run (s)"); ax[1].set_ylabel("Final test AUROC"); ax[1].set_title("Cost vs prediction", fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig_tradeoff.pdf"); plt.close(fig)
fig, ax = plt.subplots(1, 2, figsize=(7.0, 2.4))
for a in ORDER:
    for axi, k in ((ax[0], "worst"), (ax[1], "std")):
        pass
pc = {a: [[c["auroc"] for c in D[a][s]["per_client_test_at_best"]] if False else [c["auroc"] for c in R[a][s][-1]["per_client_test"]] for s in seeds] for a in ORDER}
ax[0].boxplot([np.array(pc[a]).ravel() for a in ORDER], showfliers=True, flierprops={"ms": 2})
ax[0].set_xticklabels([SHORT[a] for a in ORDER], rotation=60, ha="right"); ax[0].set_ylabel("Client AUROC (round 20)")
ax[0].axhline(.5, color="k", lw=.5, ls=":")
ax[1].bar(range(len(ORDER)), [wc[a][0] for a in ORDER], yerr=[wc[a][1] for a in ORDER], color=[COL[a] for a in ORDER], capsize=1.5, error_kw={"lw": .7})
ax[1].set_xticks(range(len(ORDER))); ax[1].set_xticklabels([SHORT[a] for a in ORDER], rotation=60, ha="right"); ax[1].set_ylabel("Worst-client AUROC")
fig.tight_layout(); fig.savefig(f"{OUT}/fig_clients.pdf"); plt.close(fig)
print("ok")
for a in ORDER: print(a, [round(ml['auroc'][a][0], 4)], round(wc[a][0], 3))
