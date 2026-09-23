param(
    [switch]$IncludeWorkingTree
)

$ErrorActionPreference = "Stop"

$gitRoot = git rev-parse --show-toplevel 2>$null
if (-not $gitRoot) {
    Write-Error "BLOCKED: this directory is not a Git repository."
    exit 2
}

$tracked = @(git -C $gitRoot ls-files)
$scopeLabel = "tracked files"
if ($IncludeWorkingTree) {
    $tracked += @(git -C $gitRoot ls-files --others --exclude-standard)
    $tracked = @($tracked | Sort-Object -Unique)
    $scopeLabel = "tracked and non-ignored working-tree files"
}
$violations = @()
foreach ($path in $tracked) {
    $normalized = $path.Replace("\", "/")
    $isPlaceholder = $normalized -match '^data/(raw|processed|reports|clustering|features)/\.gitkeep$'
    if (
        (-not $isPlaceholder) -and (
            $normalized -match '(^|/)\.env$' -or
            $normalized -match '(^|/)data/raw/' -or
            $normalized -match '(^|/)data/.*\.(csv|parquet)$' -or
            $normalized -match '(?i)(credential|secret|private|rider.*mapping|mapping.*rider|google.*response|places.*response)'
        )
    ) {
        $violations += $normalized
        continue
    }

    $fullPath = Join-Path $gitRoot $path
    if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
        $pattern = if ($normalized -match '\.(md|txt)$') { 'AIza[0-9A-Za-z_-]{20,}' } else { 'AIza[0-9A-Za-z_-]{20,}|RiderId\s*[,=:]' }
        $matches = Select-String -LiteralPath $fullPath -Pattern $pattern -SimpleMatch:$false -ErrorAction SilentlyContinue
        if ($matches) {
            $violations += "$normalized (sensitive pattern)"
        }
    }
}

if ($violations.Count -gt 0) {
    Write-Error ("FAIL: prohibited files or content found: " + ($violations -join ", "))
    exit 1
}

Write-Output ("PASS: " + $tracked.Count + " " + $scopeLabel + " stay within the safety boundary.")
exit 0
