
$ErrorActionPreference = "Continue"
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Docker is not running. Start Docker Desktop and rerun." -ForegroundColor Red; exit 1 }
if ((docker ps -q)) { Write-Host "Containers are already running. Run: docker stop `$(docker ps -q)" -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force www, www\logs | Out-Null

function fr { docker run --rm -e PYTHONPATH=/app -v "${PWD}:/app/host" --entrypoint python3 fedrag:cpu @args }

function step($name, [scriptblock]$cmd, $outdir = $null) {
    if ($outdir -and (Test-Path $outdir) -and (Get-ChildItem $outdir -Recurse -File -ErrorAction SilentlyContinue)) {
        Write-Host "SKIP (already has results): $name" -ForegroundColor DarkGray; return
    }
    Write-Host "`n=== $name  ($(Get-Date -Format HH:mm:ss)) ===" -ForegroundColor Cyan
    $log = "www\logs\{0}_{1}.log" -f $name, (Get-Date -Format HHmmss)
    & $cmd 2>&1 | ForEach-Object { $_; Add-Content -Path $log -Value $_ -ErrorAction SilentlyContinue }
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name (see $log)" -ForegroundColor Red }
    else { Write-Host "OK: $name" -ForegroundColor Green }
}

$M = @("--cohort","/app/host/work/mortality_next/cohort.pkl","--kg","/app/host/work/mortality_next/kg.pkl")
$A = @("--cohort","/app/host/work/ade_next/cohort.pkl","--kg","/app/host/work/ade_next/kg.pkl")
$S = "/app/host/fedrag_sim.py"


step "E1_scale_sources" {
    fr $S retrieval @M --clients 5 10 20 --seeds 1 2 3 --arms server client client_local fqp `
       --fqp_join_w 0.2 --out /app/host/www/scale_sources
} "www\scale_sources"

foreach ($r in 1,2,3) {
    step "E2_repl$r" {
        fr $S retrieval @M --clients 10 --seeds 1 2 3 --arms fqp --fqp_repl $r `
           --fqp_join_w 0.2 --out "/app/host/www/repl$r"
    } "www\repl$r"
}
step "E2_hops1" {
    fr $S retrieval @M --clients 10 --seeds 1 2 3 --arms fqp --fqp_hops 1 `
       --fqp_join_w 0.2 --out /app/host/www/hops1
} "www\hops1"
foreach ($j in 5,20,50) {
    step "E2_jointop$j" {
        fr $S retrieval @M --clients 10 --seeds 1 2 3 --arms fqp --fqp_join_top $j `
           --fqp_join_w 0.2 --out "/app/host/www/jointop$j"
    } "www\jointop$j"
}
foreach ($d in 0,2,5) {
    step "E3_decoys$d" {
        fr $S retrieval @M --clients 10 --seeds 1 2 3 --arms fqp --fqp_decoys $d `
           --fqp_join_w 0.2 --out "/app/host/www/decoys$d"
    } "www\decoys$d"
}
step "E4_retrieval_ade" {
    fr $S retrieval @A --clients 10 --seeds 1 2 3 --fqp_join_w 0.2 --out /app/host/www/retrieval_ade
} "www\retrieval_ade"


$llmUp = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:11434/api/tags | Out-Null; $llmUp = $true } catch {}
$agentArms = if ($llmUp) { @("local","fqp","rule","agent") } else { @("local","fqp","rule") }
if (-not $llmUp) { Write-Host "No LLM server on :11434 -> E5 without the 'agent' arm" -ForegroundColor Yellow }
step "E5_agent" {
    docker run --rm -e AGENT_LLM_URL=http://host.docker.internal:11434/v1/chat/completions `
      -e AGENT_LLM_MODEL=qwen2.5:7b -v "${PWD}:/app/host" --entrypoint python3 fedrag:cpu `
      /app/host/agent_fqp.py eval @A --clients 10 --seeds 1 2 3 --arms @agentArms `
      --max_queries 300 --fqp_join_w 0.2 --out /app/host/www/agent
} "www\agent"

step "E6_sparql_cache" {
    docker run --rm -e PYTHONPATH=/app -v "${PWD}:/app/host" -v "${PWD}\sparql_ext.py:/app/sparql_ext.py" --entrypoint python3 fedrag:cpu `
      /app/sparql_ext.py build-cache --names /app/host/work/ade_next/kg_names.pkl `
      --endpoints https://ubergraph.apps.renci.org/sparql --max-seconds 3600 --out /app/host/work/sparql_cache.pkl
}

if (Test-Path work\sparql_cache.pkl) {
    step "E6_sparql" {
        fr $S retrieval @A --clients 10 --seeds 1 2 3 --arms client fqp sparql_ext `
           --sparql_cache /app/host/work/sparql_cache.pkl --out /app/host/www/sparql
    } "www\sparql"
} else { Write-Host "work\sparql_cache.pkl missing -> skipping E6" -ForegroundColor Yellow }


step "E7_budget" {
    docker run --rm -v "${PWD}:/app/host" --entrypoint python3 fedrag:cpu `
      /app/host/extra/run_extra.py budget --budgets 4 64 --budget_arms random client
}
Write-Host "`nDone." -ForegroundColor Cyan
