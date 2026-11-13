# Fetches the os-taxonomy dataset into backend/vendor/os-taxonomy at the pinned commit.
# The pin is TAXONOMY_COMMIT in app/taxonomy/constants.py; this script only reads it.
$ErrorActionPreference = 'Stop'

$backendDir = Split-Path -Parent $PSScriptRoot
$constants = Join-Path $backendDir 'app\taxonomy\constants.py'
$target = Join-Path $backendDir 'vendor\os-taxonomy'

$text = Get-Content -Raw -Path $constants
$commitMatch = [regex]::Match($text, '(?m)^TAXONOMY_COMMIT = "([0-9a-f]{40})"')
$urlMatch = [regex]::Match($text, '(?m)^TAXONOMY_REPO_URL = "([^"]+)"')
if (-not $commitMatch.Success -or -not $urlMatch.Success) {
    throw "Could not read TAXONOMY_COMMIT and TAXONOMY_REPO_URL from $constants"
}
$commit = $commitMatch.Groups[1].Value
$repoUrl = $urlMatch.Groups[1].Value

function Invoke-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed with exit code $LASTEXITCODE" }
}

# The data files are plain git blobs, so Git LFS is not needed.
$env:GIT_LFS_SKIP_SMUDGE = '1'

if (-not (Test-Path (Join-Path $target '.git'))) {
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Invoke-Git -C $target init --quiet
    Invoke-Git -C $target remote add origin $repoUrl
}

# Fetch exactly the pinned commit, never a branch.
Invoke-Git -C $target fetch --quiet --depth 1 origin $commit
Invoke-Git -C $target -c advice.detachedHead=false checkout --quiet --force $commit

$actual = (& git -C $target rev-parse HEAD).Trim()
if ($actual -ne $commit) { throw "Checkout is at $actual, expected $commit" }
Write-Output "os-taxonomy is at $commit in $target"
