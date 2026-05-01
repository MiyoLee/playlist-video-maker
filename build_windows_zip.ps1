param(
    [string]$Python = "python",
    [string]$AppName = "playlist-video-maker",
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$BuildRoot = Join-Path $RepoRoot "build/windows"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkRoot = Join-Path $BuildRoot "work"
$ReleaseRoot = Join-Path $BuildRoot "release"
$ReleaseDir = Join-Path $ReleaseRoot $AppName
$ZipPath = Join-Path $ReleaseRoot "$AppName-windows-$Version.zip"
$EntryPoint = Join-Path $RepoRoot "src/playlist_video_maker/__main__.py"
$FontsSource = Join-Path $RepoRoot "resources/fonts"
$FontsTarget = Join-Path $ReleaseDir "resources/fonts"
$LicenseSource = Join-Path $RepoRoot "resources/fonts/source-han-sans-license/LICENSE.txt"
$LicenseTarget = Join-Path $ReleaseDir "resources/fonts/LICENSE-source-han-sans.txt"
$ReadmeTarget = Join-Path $ReleaseDir "README-Windows.txt"

if (-not (Test-Path $EntryPoint)) {
    throw "Entry point not found: $EntryPoint"
}

if (-not (Test-Path $FontsSource)) {
    throw "Bundled fonts not found: $FontsSource"
}

& $Python -m pip install pyinstaller

if (Test-Path $BuildRoot) {
    Remove-Item $BuildRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --distpath $DistRoot `
    --workpath $WorkRoot `
    --specpath $BuildRoot `
    --paths (Join-Path $RepoRoot "src") `
    --add-data "$FontsSource;resources/fonts" `
    $EntryPoint

$BuiltAppDir = Join-Path $DistRoot $AppName

if (-not (Test-Path $BuiltAppDir)) {
    throw "PyInstaller output not found: $BuiltAppDir"
}

Copy-Item $BuiltAppDir $ReleaseDir -Recurse

if (Test-Path $FontsTarget) {
    Remove-Item $FontsTarget -Recurse -Force
}

New-Item -ItemType Directory -Path (Split-Path $FontsTarget -Parent) -Force | Out-Null
Copy-Item $FontsSource $FontsTarget -Recurse

if (Test-Path $LicenseSource) {
    Copy-Item $LicenseSource $LicenseTarget -Force
}

@"
Playlist Video Maker (Windows ZIP)

1. Unzip this folder anywhere on your PC.
2. Run $AppName.exe.
3. ffmpeg and ffprobe are external in this first Windows build.
   - Put ffmpeg/bin on PATH, or
   - Set FFMPEG_PATH and FFPROBE_PATH to the full executable paths.
4. Fonts for subtitle rendering are included under resources\fonts.
5. If startup fails before the window appears, check:
   %USERPROFILE%\PlayList\playlist-video-maker-logs
"@ | Set-Content -Path $ReadmeTarget -Encoding UTF8

if (Test-Path $ZipPath) {
    Remove-Item $ZipPath -Force
}

Compress-Archive -Path $ReleaseDir -DestinationPath $ZipPath

Write-Host "Built Windows ZIP: $ZipPath"
