param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $PSScriptRoot "build"
$DistRoot = Join-Path $PSScriptRoot "dist"
$Venv = Join-Path $BuildRoot "venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$InnoScript = Join-Path $BuildRoot "installer.iss"
$WebViewBootstrapper = Join-Path $BuildRoot "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
$AppIcon = Join-Path $BuildRoot "archivist.ico"
$WizardImage = Join-Path $BuildRoot "archivist-wizard.bmp"

if ($Version -notmatch '^\d+(\.\d+){1,3}$') {
    throw "Version must be numeric, for example 1.0.0."
}
New-Item -ItemType Directory -Force -Path $BuildRoot, $DistRoot | Out-Null

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher was not found. Install 64-bit Python 3.11 and run this script again."
}
& py -3.11 -c "import struct, sys; assert struct.calcsize('P') == 8; print(sys.version)"
if ($LASTEXITCODE -ne 0) {
    throw "A 64-bit Python 3.11 installation is required."
}

if (-not (Test-Path $Python)) {
    & py -3.11 -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the build environment." }
& $Python -m pip install -r (Join-Path $RepoRoot "requirements.txt") "pyinstaller==6.14.2"
if ($LASTEXITCODE -ne 0) { throw "Could not install application or packaging dependencies." }

$LogoPath = Join-Path $RepoRoot "images\archivist.png"
$IconGenerator = @'
from PIL import Image
import sys

with Image.open(sys.argv[1]) as logo:
    logo = logo.convert("RGB")
    side = round(logo.height * 0.9)
    left = round(logo.width * 0.02)
    top = (logo.height - side) // 2
    mark = logo.crop((left, top, left + side, top + side)).resize(
        (256, 256), Image.Resampling.LANCZOS
    )
    mark.save(sys.argv[2], format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    mark.resize((55, 55), Image.Resampling.LANCZOS).save(sys.argv[3], format="BMP")
'@
$EncodedIconGenerator = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($IconGenerator))
$IconCommand = "import base64; exec(base64.b64decode('$EncodedIconGenerator'))"
& $Python -c $IconCommand $LogoPath $AppIcon $WizardImage
if ($LASTEXITCODE -ne 0) { throw "Could not create Archivist application icons from the logo." }

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "Archivist",
    "--icon", $AppIcon,
    "--distpath", $DistRoot,
    "--workpath", (Join-Path $BuildRoot "pyinstaller"),
    "--specpath", $BuildRoot,
    "--paths", $RepoRoot,
    "--add-data", "$(Join-Path $RepoRoot 'run\web\static');run\web\static",
    "--add-data", "$(Join-Path $RepoRoot 'fonts');fonts",
    "--collect-all", "webview",
    "--collect-all", "pyexiv2",
    "--collect-all", "PIL",
    "--collect-submodules", "run",
    (Join-Path $PSScriptRoot "desktop_launcher.py")
)
& $Python -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build Archivist." }

$CompilerPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
$InnoCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
)
if (-not $CompilerPath) {
    $CompilerPath = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $CompilerPath) {
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Inno Setup 6 is required. Install it from https://jrsoftware.org/isinfo.php, then rerun this script."
    }
    & $Winget.Source install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements

    $CompilerPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
    if (-not $CompilerPath) {
        $CompilerPath = $InnoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
}
if (-not $CompilerPath) { throw "Inno Setup was installed but ISCC.exe could not be located." }

if (-not (Test-Path $WebViewBootstrapper)) {
    Invoke-WebRequest `
        -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" `
        -OutFile $WebViewBootstrapper `
        -UseBasicParsing
}

$EscapedDist = $DistRoot.Replace('"', '""')
$EscapedWebView = $WebViewBootstrapper.Replace('"', '""')
$EscapedAppIcon = $AppIcon.Replace('"', '""')
$EscapedWizardImage = $WizardImage.Replace('"', '""')
$InstallerScript = @"
#define AppVersion "$Version"
#define OutputDir "$EscapedDist"
#define AppFiles "$EscapedDist\Archivist"
#define WebViewBootstrapper "$EscapedWebView"
#define AppIcon "$EscapedAppIcon"
#define WizardImage "$EscapedWizardImage"

[Setup]
AppId={{AB55B614-918D-4C92-8672-7F62868EA03F}
AppName=Archivist
AppVersion={#AppVersion}
AppPublisher=Archivist
SetupIconFile={#AppIcon}
WizardSmallImageFile={#WizardImage}
DefaultDirName={localappdata}\Programs\Archivist
UsePreviousAppDir=yes
DefaultGroupName=Archivist
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64
OutputDir={#OutputDir}
OutputBaseFilename=Archivist-Setup
UninstallDisplayIcon={app}\Archivist.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Files]
Source: "{#AppFiles}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#WebViewBootstrapper}"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\Archivist"; Filename: "{app}\Archivist.exe"
Name: "{autodesktop}\Archivist"; Filename: "{app}\Archivist.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Parameters: "/silent /install"; StatusMsg: "Installing the Microsoft Edge WebView2 Runtime..."; Flags: runhidden waituntilterminated
Filename: "{app}\Archivist.exe"; Description: "Launch Archivist"; Flags: postinstall nowait skipifsilent
"@
Set-Content -Path $InnoScript -Value $InstallerScript -Encoding UTF8

& $CompilerPath $InnoScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to create the installer." }

$InstallerPath = Join-Path $DistRoot "Archivist-Setup.exe"
if (-not (Test-Path $InstallerPath)) { throw "The installer was not created at $InstallerPath." }
Write-Host "Installer created: $InstallerPath"
