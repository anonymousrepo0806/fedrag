
Set-Location (Join-Path $PSScriptRoot "..")
$results = "results"
if (Test-Path ".env") { foreach ($line in Get-Content ".env") { if ($line -match '^\s*RESULTS_HOST\s*=\s*(.+)$') { $results = $Matches[1].Trim() } } }
$abs = (Resolve-Path $results).Path
docker run --rm -v "${abs}:/results" --entrypoint python fedrag:cpu fedrag_sim.py tables --results /results --out /results/tables.tex
Get-ChildItem $abs -Directory -Filter "sim_*" | ForEach-Object {
  docker run --rm -v "${abs}:/results" --entrypoint python fedrag:cpu fedrag_sim.py tables --results "/results/$($_.Name)" --out "/results/$($_.Name)/tables.tex" }
