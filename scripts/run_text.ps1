



param([string]$Section = "diagnosis", [int[]]$ClientCounts = @(10), [int[]]$Seeds = @(1, 2, 3), [int]$Rounds = 5,
      [int]$Threads = 4, [int]$MaxTrain = 400, [int]$MaxTest = 100, [string]$HideDx = "0 1",
      [string]$Model = "google/flan-t5-small")
Set-Location (Join-Path $PSScriptRoot "..")
$cfg = @{ MIMIC_HOST = "./data/mimic3"; KG_HOST = "./GraphCare-main/KG_mapping"; KG_RES_HOST = "./GraphCare-main/resources";
          WORK_HOST = "./work"; RESULTS_HOST = "./results" }
if (Test-Path ".env") { foreach ($line in Get-Content ".env") { if ($line -match '^\s*([A-Z_]+)\s*=\s*(.+)$' -and $cfg.ContainsKey($Matches[1])) { $cfg[$Matches[1]] = $Matches[2].Trim() } } }
foreach ($k in "WORK_HOST", "RESULTS_HOST") { New-Item -ItemType Directory -Force -Path $cfg[$k] | Out-Null }
$abs = @{}; foreach ($k in $cfg.Keys) { $abs[$k] = (Resolve-Path $cfg[$k]).Path }
docker compose build -q
$v = @("-v", "$($abs.MIMIC_HOST):/mimic:ro", "-v", "$($abs.KG_HOST):/kg:ro", "-v", "$($abs.KG_RES_HOST):/kg_resources:ro",
       "-v", "$($abs.WORK_HOST):/work", "-v", "$($abs.RESULTS_HOST):/results", "-e", "HF_HOME=/work/hf", "-e", "KG_RESOURCES=/kg_resources")
function Sim { param([string[]]$Args2) docker run --rm @v --entrypoint python fedrag:cpu fedrag_sim.py @Args2; if ($LASTEXITCODE) { throw "step failed: $Args2" } }
$T = "notes_$Section"; $W = "/work/$T"; $R = "/results/text_$T"
if (-not (Test-Path "$($abs.WORK_HOST)/measurements.pkl")) { Sim @("measurements", "--mimic", "/mimic", "--out", "/work/measurements.pkl") }
if (-not (Test-Path "$($abs.WORK_HOST)/$T/cohort.pkl")) { Sim @("notes", "--mimic", "/mimic", "--section", $Section, "--measurements", "/work/measurements.pkl", "--out", "$W/cohort.pkl") }
if (-not (Test-Path "$($abs.WORK_HOST)/$T/kg.pkl"))     { Sim @("kg", "--cohort", "$W/cohort.pkl", "--kgdir", "/kg", "--out", "$W/kg.pkl") }
$extra = "--tg_model $Model --tg_max_train $MaxTrain --tg_max_test $MaxTest"
Sim (@("sweep_text", "--cohort", "$W/cohort.pkl", "--kg", "$W/kg.pkl", "--kgdir", "/kg", "--out", $R, "--rounds", "$Rounds",
       "--task_tag", $T, "--threads", "$Threads", "--extra", $extra, "--clients") + ($ClientCounts | ForEach-Object { "$_" }) +
     @("--seeds") + ($Seeds | ForEach-Object { "$_" }) + @("--hide_dx") + ($HideDx.Split(" ")))
Sim @("tables", "--results", $R, "--out", "$R/tables.tex")
Write-Host "Tables: $($cfg.RESULTS_HOST)/text_$T/tables.tex   examples: *.examples.json   every metric: all_text_runs.csv"
