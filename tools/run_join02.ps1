param(
    [string]$Vvp,
    [string]$Simulation,
    [string]$Executable,
    [Parameter(Mandatory = $true)][string]$Manifest,
    [Parameter(Mandatory = $true)][string]$ImageRoot,
    [int]$NoRetireCycles = 100000
)

if ([string]::IsNullOrWhiteSpace($Executable) -and
    ([string]::IsNullOrWhiteSpace($Vvp) -or [string]::IsNullOrWhiteSpace($Simulation))) {
    throw "JOIN-02 requires either -Executable or both -Vvp and -Simulation"
}

$rows = @(
    Get-Content -LiteralPath $Manifest |
        Where-Object { $_.Trim() -ne "" -and -not $_.Trim().StartsWith("#") } |
        ForEach-Object {
            $fields = $_.Split(",")
            if ($fields.Count -ne 4) { throw "JOIN-02 manifest row must contain four fields: $_" }
            [pscustomobject]@{
                Name = $fields[0].Trim()
                Expected = [int]$fields[1]
                MaxCycles = [int]$fields[2]
            }
        }
)

if ($rows.Count -ne 18) {
    throw "JOIN-02 requires exactly 18 manifest images; found $($rows.Count)"
}

foreach ($row in $rows) {
    $image = Join-Path $ImageRoot "$($row.Name).data"
    if (-not (Test-Path -LiteralPath $image -PathType Leaf)) {
        throw "JOIN-02 image is missing: $image"
    }

    $arguments = @(
        "+IMAGE=$image"
        "+TEST=$($row.Name)"
        "+EXPECTED=$($row.Expected)"
        "+MAX_CYCLES=$($row.MaxCycles)"
        "+MAX_NO_RETIRE_CYCLES=$NoRetireCycles"
    )
    if ([string]::IsNullOrWhiteSpace($Executable)) {
        $output = & $Vvp -N $Simulation @arguments 2>&1
    } else {
        $output = & $Executable @arguments 2>&1
    }
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0 -or $outputText -notmatch "PASS: JOIN-02 image=$($row.Name) ") {
        throw "JOIN-02 image failed: $($row.Name)"
    }
}

Write-Host "PASS: JOIN-02 all 18 images halted with expected return values"
