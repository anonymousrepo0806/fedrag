import argparse
import os
import subprocess
import sys

H = "/app/host"
FS = H + "/fedrag_sim.py" if os.path.exists(H + "/fedrag_sim.py") else "/app/fedrag_sim.py"
os.environ["PYTHONPATH"] = "/app" + os.pathsep + os.environ.get("PYTHONPATH", "")
ARMS_MAIN = ["none", "random", "server", "client", "client_kgc", "server_ctx", "client_local", "fqp"]


def run(args):
    print("RUN", " ".join(args), flush=True)
    r = subprocess.run([sys.executable, FS] + args)
    if r.returncode:
        raise SystemExit("step failed: " + " ".join(args))


def common(a):
    return ["--partition", "noniid", "--alpha", "0.5", "--clients", "10", "--rounds", "20"]


def part_seeds(a):
    run(["sweep", "--cohort", f"{H}/work/mortality_next/cohort.pkl", "--kg", f"{H}/work/mortality_next/kg.pkl",
         "--partition", "noniid", "--alpha", "0.5", "--grid", "main", "--clients", "10",
         "--seeds"] + [str(s) for s in a.seeds_all] + ["--fqp_join_w", "0.2", "--out", f"{H}/sweep_main_v2"])


def part_budget(a):
    for b in a.budgets:
        out = f"{H}/ablation_budget/b{b}"
        os.makedirs(out, exist_ok=True)
        for arm in a.budget_arms:
            for s in a.seeds:
                tag = f"mimic__fedavg__sage__{arm}__c10__noniid__seed{s}"
                if os.path.exists(os.path.join(out, tag + ".summary.json")):
                    print("skip (done)", b, tag, flush=True)
                    continue
                run(["train", "--cohort", f"{H}/work/mortality_next/cohort.pkl", "--kg", f"{H}/work/mortality_next/kg.pkl",
                     "--arm", arm, "--fl", "fedavg", "--model", "sage", "--seed", str(s), "--budget", str(b),
                     "--out", out] + common(a))


def part_ade(a):
    wd = f"{H}/work/ade_next"
    os.makedirs(wd, exist_ok=True)
    mimic = f"{H}/data/mimic3"
    meas = f"{H}/work/measurements.pkl"
    excl = f"{H}/data/user_data/reserved_subjects.txt"
    cohort, kg = f"{wd}/cohort.pkl", f"{wd}/kg.pkl"
    if not os.path.exists(cohort):
        cmd = ["build", "--mimic", mimic, "--task", "ade_next", "--out", cohort]
        if os.path.exists(meas):
            cmd += ["--measurements", meas]
        if os.path.exists(excl):
            cmd += ["--exclude_file", excl]
        run(cmd)
    if not os.path.exists(kg):
        run(["kg", "--cohort", cohort, "--kgdir", f"{H}/GraphCare-main/KG_mapping", "--out", kg])
    for grid in (["main", "graph"] if a.part != "ade_graph" else ["graph"]):
        run(["sweep", "--cohort", cohort, "--kg", kg, "--partition", "noniid", "--alpha", "0.5", "--grid", grid,
             "--clients", "10", "--seeds"] + [str(s) for s in a.seeds] + ["--task_tag", "ade_next", "--fqp_join_w", "0.2",
                                                                          "--out", f"{H}/sweep_ade_v2"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("part", choices=["seeds", "budget", "ade", "ade_graph", "all"])
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--seeds_all", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--budgets", type=int, nargs="+", default=[4, 64])
    p.add_argument("--budget_arms", nargs="+", default=["random", "client"])
    a = p.parse_args()
    if a.part in ("seeds", "all"):
        part_seeds(a)
    if a.part in ("budget", "all"):
        part_budget(a)
    if a.part in ("ade", "ade_graph", "all"):
        part_ade(a)


if __name__ == "__main__":
    main()
