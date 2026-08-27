param(
    [Parameter(Mandatory = $true)][string]$Vvp,
    [Parameter(Mandatory = $true)][string]$Simulation,
    [Parameter(Mandatory = $true)][string]$Manifest,
    [Parameter(Mandatory = $true)][string]$ImageRoot
)

$names = @(
    Get-Content -LiteralPath $Manifest |
        Where-Object { $_.Trim() -ne "" -and -not $_.Trim().StartsWith("#") } |
        ForEach-Object { ($_.Split(",")[0]).Trim() }
)

if ($names.Count -ne 18) {
    throw "A-07 requires exactly 18 manifest images; found $($names.Count)"
}

foreach ($name in $names) {
    $image = Join-Path $ImageRoot "$name.data"
    if (-not (Test-Path -LiteralPath $image -PathType Leaf)) {
        throw "A-07 image is missing: $image"
    }

    $output = & $Vvp -N $Simulation "+IMAGE=$image" 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    if ($exitCode -ne 0 -or $outputText -notmatch "PASS: A-07 image fetch smoke") {
        $output | ForEach-Object { Write-Host $_ }
        throw "A-07 image fetch failed: $name"
    }
}

Write-Host "PASS: A-07 fetched all 18 manifest images through frontend/cache/bridge"
