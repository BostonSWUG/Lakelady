# Lakelady Installer
# Run this once to set up Lakelady and create a desktop shortcut.
# Right-click > "Run with PowerShell" or run from terminal.

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Lakelady Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "Checking Python..." -NoNewline
try {
    $pyVersion = python --version 2>&1
    Write-Host " $pyVersion" -ForegroundColor Green
} catch {
    Write-Host " NOT FOUND" -ForegroundColor Red
    Write-Host ""
    Write-Host "Python 3.10+ is required. Download from:"
    Write-Host "  https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Make sure to check 'Add Python to PATH' during installation."
    Read-Host "Press Enter to exit"
    exit 1
}

# Install dependencies
Write-Host "Installing Python dependencies..."
pip install -r "$scriptDir\requirements.txt" --quiet
if ($LASTEXITCODE -eq 0) {
    New-Item -Path "$scriptDir\.deps_installed" -ItemType File -Force | Out-Null
    Write-Host "  Dependencies installed." -ForegroundColor Green
} else {
    Write-Host "  ERROR: pip install failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check Firefox + geckodriver
Write-Host "Checking Firefox..." -NoNewline
$firefox = Get-Command firefox -ErrorAction SilentlyContinue
if ($firefox) {
    Write-Host " Found" -ForegroundColor Green
} else {
    Write-Host " NOT FOUND" -ForegroundColor Yellow
    Write-Host "  Firefox is required for Agile PLM automation."
    Write-Host "  Download from: https://www.mozilla.org/firefox/" -ForegroundColor Yellow
}

Write-Host "Checking geckodriver..." -NoNewline
$geckodriver = Get-Command geckodriver -ErrorAction SilentlyContinue
if ($geckodriver) {
    Write-Host " Found" -ForegroundColor Green
} else {
    Write-Host " NOT FOUND" -ForegroundColor Yellow
    Write-Host "  geckodriver is required for Selenium."
    Write-Host "  Download from: https://github.com/mozilla/geckodriver/releases" -ForegroundColor Yellow
    Write-Host "  Place geckodriver.exe in your PATH or in the Lakelady folder."
}

# Create desktop shortcut
Write-Host ""
Write-Host "Creating desktop shortcut..."
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Lakelady.lnk"
$batPath = Join-Path $scriptDir "Lakelady.bat"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $batPath
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "Lakelady - Agile PLM File Automation"
$shortcut.Save()

Write-Host "  Shortcut created: $shortcutPath" -ForegroundColor Green

# Done
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To run Lakelady:"
Write-Host "  - Double-click 'Lakelady' on your Desktop"
Write-Host "  - Or double-click Lakelady.bat in this folder"
Write-Host ""
Read-Host "Press Enter to exit"
