

param([string]$Task = "mortality_next", [int[]]$Seeds = @(1, 2, 3), [int[]]$ClientCounts = @(10), [int]$Rounds = 20)
Set-Location (Join-Path $PSScriptRoot "..")
$combos = "fedavg:sage:none", "fedavg:sage:random", "fedavg:sage:server", "fedavg:sage:client",
          "fedavg:sage:client_local", "fedavg:sage:fqp", "ewckd:sage:fqp", "fedprox:sage:fqp",
          "fedprox:sage:none", "fedprox:sage:server", "fedprox:sage:client",
          "fedcurv:sage:none", "fedcurv:sage:server", "fedcurv:sage:client",
          "fedlwf:sage:none", "fedlwf:sage:server", "fedlwf:sage:client",
          "ewckd:sage:none", "ewckd:sage:server", "ewckd:sage:client",
          "fedavg:bag:none", "fedavg:bag:client", "fedavg:retain:none", "fedavg:retain:client",
          "fedavg:transformer:none", "fedavg:transformer:client"
foreach ($seed in $Seeds) { foreach ($k in $ClientCounts) { foreach ($c in $combos) {
  $fl, $model, $arm = $c.Split(":")
  $hyp = if ($fl -eq "fedavg" -and $model -eq "sage" -and ($arm -eq "client" -or $arm -eq "none" -or $arm -eq "fqp")) { 1 } else { 0 }
  & "$PSScriptRoot\docker_run.ps1" -Task $Task -Fl $fl -Model $model -Arm $arm -Clients $k -Seed $seed -Rounds $Rounds -Hypotheses $hyp
}
  
  foreach ($arm in "none", "server", "client", "fqp") {
    & "$PSScriptRoot\docker_run.ps1" -Task $Task -Fl fedavg -Model sage -Arm $arm -Clients $k -Seed $seed -Rounds $Rounds -Hypotheses 0 -Meas 0
  }
}}
& "$PSScriptRoot\make_tables.ps1"
