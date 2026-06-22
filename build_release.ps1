# Build Lakelady release zip
# Creates a distributable zip file with everything needed to run Lakelady.

$version = "2.1.1"
$outputName = "Lakelady_v$version"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputDir = Join-Path $scriptDir "dist"
$zipPath = Join-Path $outputDir "$outputName.zip"

# Create dist folder
New-Item -Path $outputDir -ItemType Directory -Force | Out-Null

# Files to include
$includeFiles = @(
    "app.py",
    "lakelady.py",
    "requirements.txt",
    "Lakelady.bat",
    "lakelady.ico",
    "install.ps1",
    "README.txt",
    ".gitignore"
)

# Create temp staging folder
$stagingDir = Join-Path $outputDir $outputName
if (Test-Path $stagingDir) { Remove-Item $stagingDir -Recurse -Force }
New-Item -Path $stagingDir -ItemType Directory -Force | Out-Null

# Copy files
foreach ($file in $includeFiles) {
    $src = Join-Path $scriptDir $file
    if (Test-Path $src) {
        Copy-Item $src -Destination $stagingDir
        Write-Host "  Added: $file"
    } else {
        Write-Host "  SKIPPED (not found): $file" -ForegroundColor Yellow
    }
}

# Create zip
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$stagingDir\*" -DestinationPath $zipPath
Remove-Item $stagingDir -Recurse -Force

Write-Host ""
Write-Host "Built: $zipPath" -ForegroundColor Green
Write-Host "Size: $([math]::Round((Get-Item $zipPath).Length / 1KB, 1)) KB"
