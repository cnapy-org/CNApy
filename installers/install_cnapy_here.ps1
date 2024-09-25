# Adapted from https://raw.githubusercontent.com/mamba-org/micromamba-releases/main/install.ps1

$CNAPY_VERSION = "1.2.1.1"  # Replace with the actual version if needed
$RELEASE_URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64"

Write-Output "Downloading micromamba from $RELEASE_URL"
curl.exe -L -o micromamba.exe $RELEASE_URL

# Get the directory where the script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$InstallDir = Join-Path -Path $ScriptDir -ChildPath "cnapy-$CNAPY_VERSION"
New-Item -ItemType Directory -Force -Path $InstallDir | out-null

$MAMBA_INSTALL_PATH = Join-Path -Path $InstallDir -ChildPath "micromamba.exe"

Write-Output "`nInstalling micromamba to $InstallDir`n"
Move-Item -Force micromamba.exe $MAMBA_INSTALL_PATH | out-null

# Use & to execute the micromamba commands stored in the variable
& $MAMBA_INSTALL_PATH create -y -p "./cnapy-$CNAPY_VERSION/cnapy-environment" python=3.10 pip -r "./cnapy-$CNAPY_VERSION/"
& $MAMBA_INSTALL_PATH run -p "./cnapy-$CNAPY_VERSION/cnapy-environment" -r "./cnapy-$CNAPY_VERSION/" pip install --no-cache-dir uv
& $MAMBA_INSTALL_PATH run -p "./cnapy-$CNAPY_VERSION/cnapy-environment" -r "./cnapy-$CNAPY_VERSION/" uv --no-cache pip install --no-cache-dir cnapy

# Create a new batch file called "RUN_CNApy.bat"
$BatchFilePath = Join-Path -Path $InstallDir -ChildPath "RUN_CNApy.bat"
$BatchFileContent = "@echo off`n" + "& `"$MAMBA_INSTALL_PATH`" run -p `".\cnapy-$CNAPY_VERSION\cnapy-environment`" -r `".\cnapy-$CNAPY_VERSION\`" cnapy"
Set-Content -Path $BatchFilePath -Value $BatchFileContent

# Create desktop icon using PowerShell
$ShortcutPath = [System.IO.Path]::Combine($Env:USERPROFILE, "Desktop", "CNApy-$CNAPY_VERSION.lnk")
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $BatchFilePath
# $Shortcut.IconLocation = Join-Path -Path $ScriptDir -ChildPath "icon\CNApy_Icon.ico"
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Save()

Write-Output "`nDesktop shortcut created successfully`n"
