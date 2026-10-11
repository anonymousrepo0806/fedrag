


param(
  [string]$Task = "mortality_next", [string]$Arm = "client", [string]$Fl = "fedavg",
  [string]$Model = "sage", [int]$Clients = 10, [int]$Seed = 1, [string]$Partition = "noniid",
  [int]$Rounds = 20, [int]$Hypotheses = 1, [int]$FqpHops = 2, [int]$FqpDecoys = 0, [int]$FqpRepl = 2, [int]$HideDx = 0, [int]$Meas = 1, [switch]$Force
)
Set-Location (Join-Path $PSScriptRoot "..")
$env:TASK = $Task; $env:ARM = $Arm; $env:FL = $Fl; $env:MODEL = $Model; $env:CLIENTS = "$Clients"
$env:SEED = "$Seed"; $env:PARTITION = $Partition; $env:ROUNDS = "$Rounds"; $env:HYPOTHESES = "$Hypotheses"
$env:FQP_HOPS = "$FqpHops"; $env:FQP_DECOYS = "$FqpDecoys"; $env:FQP_REPL = "$FqpRepl"; $env:HIDE_DX = "$HideDx"; $env:MEAS = "$Meas"

$results = "results"
if (Test-Path ".env") { foreach ($line in Get-Content ".env") { if ($line -match '^\s*RESULTS_HOST\s*=\s*(.+)$') { $results = $Matches[1].Trim() } } }
New-Item -ItemType Directory -Force -Path $results | Out-Null
$sfx = ""
if ($Arm -eq "fqp" -and $FqpHops -ne 2) { $sfx += "_h$FqpHops" }
if ($Arm -eq "fqp" -and $FqpDecoys -ne 0) { $sfx += "_d$FqpDecoys" }
if (($Arm -eq "fqp" -or $Arm -eq "client_local") -and $FqpRepl -ne 2) { $sfx += "_r$FqpRepl" }
if ($Task -like "notes*" -and $HideDx -ne 0) { $sfx += "_hidedx" }
if ($Meas -eq 0) { $sfx += "_nomeas" }
if ($Task -like "notes*") { $tag = "${Task}__${Fl}__t5lora__${Arm}${sfx}__c${Clients}__${Partition}__seed${Seed}" }
else { $tag = "${Task}__${Fl}__${Model}__${Arm}${sfx}__c${Clients}__${Partition}__seed${Seed}" }
if ((Test-Path "$results/$tag.summary.json") -and -not $Force) { Write-Host "skip (done) $tag"; exit 0 }
$project = "fedrag_" + $PID

docker compose -p $project build -q;            if ($LASTEXITCODE) { exit 1 }
docker compose -p $project run --rm prep;       if ($LASTEXITCODE) { Write-Error "prep failed - see the messages above"; exit 1 }

$statsFile = (Resolve-Path $results).Path + "\$tag.docker_stats.csv"
$stats = Start-Job -ScriptBlock {
  param($out)
  "time,container,cpu_perc,mem_usage,mem_perc,net_io,block_io,pids" | Out-File $out -Encoding utf8
  while ($true) {
    $t = [DateTimeOffset]::Now.ToUnixTimeSeconds()
    docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}" |
      Where-Object { $_ -match "server|client" } | ForEach-Object { "$t,$_" } | Out-File $out -Append -Encoding utf8
    Start-Sleep 5
  }
} -ArgumentList $statsFile

$start = Get-Date
docker compose -p $project up -d --no-deps server
docker compose -p $project up -d --no-deps --scale client=$Clients client
$sid = docker compose -p $project ps -q server
docker wait $sid | Out-Null
$secs = [int]((Get-Date) - $start).TotalSeconds
docker compose -p $project logs --no-color *> "$results/$tag.containers.log"
Stop-Job $stats; Remove-Job $stats
docker compose -p $project down -v --remove-orphans | Out-Null
"{""tag"": ""$tag"", ""wall_s"": $secs}" | Out-File "$results/$tag.docker_wall.json" -Encoding ascii
if (Test-Path "$results/$tag.summary.json") { Write-Host "finished $tag in $secs s -> $results" }
else { Write-Warning "no summary for $tag - check $results/$tag.containers.log" }
