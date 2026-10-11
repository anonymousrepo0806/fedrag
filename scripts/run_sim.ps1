


param([string]$Task = "mortality_next", [int[]]$ClientCounts = @(10), [int[]]$Seeds = @(1, 2, 3),
      [int]$Rounds = 20, [string]$Grid = "all", [int]$Threads = 4, [int]$KgcRounds = 10)
Set-Location (Join-Path $PSScriptRoot "..")
$cfg = @{ MIMIC_HOST = "./data/mimic3"; KG_HOST = "./GraphCare-main/KG_mapping"; KG_RES_HOST = "./GraphCare-main/resources";
          USER_DATA_HOST = "./data/user_data"; WORK_HOST = "./work"; RESULTS_HOST = "./results" }
if (Test-Path ".env") { foreach ($line in Get-Content ".env") { if ($line -match '^\s*([A-Z_]+)\s*=\s*(.+)$' -and $cfg.ContainsKey($Matches[1])) { $cfg[$Matches[1]] = $Matches[2].Trim() } } }
foreach ($k in "WORK_HOST", "RESULTS_HOST", "USER_DATA_HOST") { New-Item -ItemType Directory -Force -Path $cfg[$k] | Out-Null }
$abs = @{}; foreach ($k in $cfg.Keys) { $abs[$k] = (Resolve-Path $cfg[$k]).Path }
docker compose build -q
$v = @("-v", "$($abs.MIMIC_HOST):/mimic:ro", "-v", "$($abs.KG_HOST):/kg:ro", "-v", "$($abs.KG_RES_HOST):/kg_resources:ro",
       "-v", "$($abs.USER_DATA_HOST):/user:ro", "-v", "$($abs.WORK_HOST):/work", "-v", "$($abs.RESULTS_HOST):/results")
function Sim { param([string[]]$Args2) docker run --rm @v --entrypoint python fedrag:cpu fedrag_sim.py @Args2; if ($LASTEXITCODE) { throw "step failed: $Args2" } }
$W = "/work/$Task"; $R = "/results/sim_$Task"
if (-not (Test-Path "$($abs.WORK_HOST)/measurements.pkl")) { Sim @("measurements", "--mimic", "/mimic", "--out", "/work/measurements.pkl") }
if (-not (Test-Path "$($abs.WORK_HOST)/$Task/cohort.pkl")) { Sim @("build", "--mimic", "/mimic", "--task", $Task, "--exclude_file", "/user/reserved_subjects.txt", "--measurements", "/work/measurements.pkl", "--out", "$W/cohort.pkl") }
if (-not (Test-Path "$($abs.WORK_HOST)/$Task/kg.pkl"))     { Sim @("kg", "--cohort", "$W/cohort.pkl", "--kgdir", "/kg", "--user_data", "/user", "--out", "$W/kg.pkl") }
if (-not (Test-Path "$($abs.RESULTS_HOST)/sim_$Task/retrieval.json")) {
  Sim (@("retrieval", "--cohort", "$W/cohort.pkl", "--kg", "$W/kg.pkl", "--out", "$R/retrieval.json", "--clients") + ($ClientCounts | ForEach-Object { "$_" }) + @("--seeds") + ($Seeds | ForEach-Object { "$_" })) }
Sim (@("sweep", "--cohort", "$W/cohort.pkl", "--kg", "$W/kg.pkl", "--out", $R, "--grid", $Grid, "--rounds", "$Rounds",
       "--task_tag", $Task, "--threads", "$Threads", "--kgc_rounds", "$KgcRounds", "--user_data", "/user", "--hypotheses",
       "--clients") + ($ClientCounts | ForEach-Object { "$_" }) + @("--seeds") + ($Seeds | ForEach-Object { "$_" }))
Sim @("tables", "--results", $R, "--out", "$R/tables.tex")
Write-Host "Tables: $($cfg.RESULTS_HOST)/sim_$Task/tables.tex   every metric: $($cfg.RESULTS_HOST)/sim_$Task/all_runs.csv"
