param(
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Parameter(Mandatory=$true)][string]$NativeAudit,
    [int[]]$WaitProcess = @()
)
$ErrorActionPreference='Stop'
$env:TEMP='F:/CPU2026Temp'
$env:TMP='F:/CPU2026Temp'
$area=Join-Path $OutputRoot 'area'
if(Test-Path -LiteralPath $area){throw 'Preserve prior PPA evidence; this runner only starts an unmeasured candidate'}
Write-Output "Native work preserved; wait predecessor jobs $($WaitProcess -join ',') before full CPU PPA"
foreach($predecessor in $WaitProcess){
    while(Get-Process -Id $predecessor -ErrorAction SilentlyContinue){Start-Sleep -Seconds 30}
}
while((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory -lt 8000000){Start-Sleep -Seconds 30}
$audit=Get-Content -LiteralPath $NativeAudit -Raw|ConvertFrom-Json
if($audit.status -ne 'VERIFIED' -or $audit.cases -ne 29){throw 'Independent original29 native audit required'}
if(!$audit.input_sha256){throw 'Native input hash inventory required'}
foreach($entry in $audit.input_sha256.PSObject.Properties){
    if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.ToLowerInvariant()){throw "Native evidence input changed: $($entry.Name)"}
}
$extraPath=Join-Path $OutputRoot 'legal_addi_native/report.json'
$extra=Get-Content -LiteralPath $extraPath -Raw|ConvertFrom-Json
if($extra.status -ne 'COMPLETE' -or $extra.results.Count -ne 8 -or $extra.memory_latency -ne 20){throw 'Additional8 ADDI255 cases required'}
foreach($row in $extra.results){if($row.status -ne 'PASS' -or $row.result -ne 256){throw 'Additional ADDI255 case failed'}}
foreach($entry in $extra.input_sha256.PSObject.Properties){
    if((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.ToLowerInvariant()){throw "Additional native evidence changed: $($entry.Name)"}
}
$manifestPath=Join-Path $OutputRoot 'build/build_manifest.json'
$manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
if(@($manifest.source_sha256.PSObject.Properties).Count -ne 43){throw 'All43 compiled inputs required'}
foreach($entry in $manifest.source_sha256.PSObject.Properties){
    if((Get-FileHash -LiteralPath (Join-Path $SourceRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.ToLowerInvariant()){throw "Frozen CPU source changed: $($entry.Name)"}
}
$bench=Get-Content -LiteralPath (Join-Path $OutputRoot 'benchmark.json') -Raw|ConvertFrom-Json
if($bench.status -ne 'COMPLETE' -or $bench.geomean_ipc -lt 1.0985){throw 'Complete qualifying benchmark IPC required'}
Write-Output 'START full CPU PPA from preserved37 native cases and exact frozen build'
Set-Location $SourceRoot
& python tools/run_course_axi_area.py --build-manifest $manifestPath --outdir $area --clock-period 2
if($LASTEXITCODE -ne 0){throw 'Full CPU area failed'}
& python tools/verify_course_axi_area.py $area --require-current
if($LASTEXITCODE -ne 0){throw 'Independent complete area audit failed'}
& python tools/run_course_full_timing.py $area --clock-port clock
if($LASTEXITCODE -ne 0){throw 'All-SRAM timing failed'}
& python E:/Verilog_cpu/tools/collect_verified_course_cpu.py $OutputRoot --source-root $SourceRoot --area $area --out (Join-Path $OutputRoot 'verified_cpu_result.json')
if($LASTEXITCODE -ne 0){throw 'Same-build complete CPU result collection failed'}
Write-Output 'COMPLETE full CPU tradeoff; no automatic source adoption'
