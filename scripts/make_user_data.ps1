



param([int]$Clients = 10, [double]$Fraction = 0.10, [int]$Seed = 0)
Set-Location (Join-Path $PSScriptRoot "..")
$mimic = "./data/mimic3"; $user = "./data/user_data"; $work = "./work"
if (Test-Path ".env") { foreach ($line in Get-Content ".env") {
  if ($line -match '^\s*MIMIC_HOST\s*=\s*(.+)$') { $mimic = $Matches[1].Trim() }
  if ($line -match '^\s*USER_DATA_HOST\s*=\s*(.+)$') { $user = $Matches[1].Trim() }
  if ($line -match '^\s*WORK_HOST\s*=\s*(.+)$') { $work = $Matches[1].Trim() } } }
New-Item -ItemType Directory -Force -Path $user, $work | Out-Null
$m = (Resolve-Path $mimic).Path; $u = (Resolve-Path $user).Path; $w = (Resolve-Path $work).Path
docker compose build -q
docker run --rm -v "${m}:/mimic:ro" -v "${u}:/user" -v "${w}:/work" --entrypoint python fedrag:cpu fedrag_sim.py user_data `
  --mimic /mimic --clients $Clients --fraction $Fraction --seed $Seed --measurements /work/measurements.pkl --out /user
Write-Host "Now delete the old cohorts (keep work\measurements.pkl, it is reused) so they are rebuilt without these patients:"
Write-Host "  Get-ChildItem work -Exclude measurements.pkl,measurements.stats.json,hf | Remove-Item -Recurse"
