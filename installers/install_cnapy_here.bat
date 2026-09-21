@echo off
setlocal

:: Optional first argument: a git branch of https://github.com/cnapy-org/CNApy to install
:: instead of the pinned PyPI release. Example: install_cnapy_here.bat cnapy2
set "BRANCH=%~1"

if /i "%BRANCH%"=="-h" goto :usage
if /i "%BRANCH%"=="--help" goto :usage
if /i "%BRANCH%"=="/?" goto :usage
goto :afterusage

:usage
echo Usage: %~n0.bat [branch]
echo   branch   Optional. A branch of https://github.com/cnapy-org/CNApy to install
echo            instead of the latest release from PyPI, e.g. "cnapy2".
exit /b 0

:afterusage

if defined BRANCH (
    where git >nul 2>nul
    if errorlevel 1 (
        echo ERROR: installing from a specific branch requires Git to be installed and available on PATH.
        echo Download Git for Windows from https://git-scm.com/download/win and try again.
        pause
        exit /b 1
    )
    echo Checking that branch "%BRANCH%" exists in https://github.com/cnapy-org/CNApy.git ...
    git ls-remote --exit-code --heads https://github.com/cnapy-org/CNApy.git "%BRANCH%" >nul 2>nul
    if errorlevel 1 (
        echo ERROR: branch "%BRANCH%" was not found in https://github.com/cnapy-org/CNApy.git
        pause
        exit /b 1
    )
    set "INSTALL_LABEL=%BRANCH:/=-%"
) else (
    set "INSTALL_LABEL=1.2.8"
)

:: Set the PowerShell script file name
set "psFile=install_cnapy.ps1"

:: Write the PowerShell script to a file.
::
:: Uses the Miniforge installer (https://github.com/conda-forge/miniforge) instead of a bare
:: micromamba.exe. Downloading a standalone, unsigned exe and immediately running it is exactly
:: the pattern many corporate EDR/AV products silently block. The Miniforge installer is signed
:: and still bundles mamba, so environment creation stays fast.
echo $ErrorActionPreference = "Stop" > "%psFile%"
echo. >> "%psFile%"
echo function Invoke-WithRetry { >> "%psFile%"
echo     param( >> "%psFile%"
echo         [ScriptBlock]$Action, >> "%psFile%"
echo         [string]$Description, >> "%psFile%"
echo         [int]$MaxAttempts = 3 >> "%psFile%"
echo     ) >> "%psFile%"
echo     for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) { >> "%psFile%"
echo         ^& $Action >> "%psFile%"
echo         if ($LASTEXITCODE -eq 0) { return } >> "%psFile%"
echo         Write-Output "$Description failed (exit code $LASTEXITCODE) on attempt $attempt of $MaxAttempts. This is often caused by antivirus software briefly locking newly created files; retrying in 5 seconds..." >> "%psFile%"
echo         if ($attempt -lt $MaxAttempts) { Start-Sleep -Seconds 5 } >> "%psFile%"
echo     } >> "%psFile%"
echo     Write-Output "ERROR: $Description failed after $MaxAttempts attempts (exit code $LASTEXITCODE)." >> "%psFile%"
echo     pause >> "%psFile%"
echo     exit 1 >> "%psFile%"
echo } >> "%psFile%"
echo. >> "%psFile%"
echo ^# Set by install_cnapy_here.bat: either the pinned release version, or a sanitized >> "%psFile%"
echo ^# branch name if one was passed as an argument to install_cnapy_here.bat. >> "%psFile%"
echo $InstallLabel = "%INSTALL_LABEL%" >> "%psFile%"
echo $RELEASE_URL = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe" >> "%psFile%"
echo. >> "%psFile%"
echo ^# Get the directory where the script is located >> "%psFile%"
echo $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path >> "%psFile%"
echo. >> "%psFile%"
echo $InstallDir = Join-Path -Path $ScriptDir -ChildPath "cnapy-$InstallLabel" >> "%psFile%"
echo New-Item -ItemType Directory -Force -Path $InstallDir ^| out-null >> "%psFile%"
echo. >> "%psFile%"
echo $InstallerPath = Join-Path -Path $InstallDir -ChildPath "miniforge_installer.exe" >> "%psFile%"
echo $MiniforgeDir = Join-Path -Path $InstallDir -ChildPath "miniforge3" >> "%psFile%"
echo $EnvDir = Join-Path -Path $InstallDir -ChildPath "cnapy-environment" >> "%psFile%"
echo $PythonExe = Join-Path -Path $EnvDir -ChildPath "python.exe" >> "%psFile%"
echo $MambaBat = Join-Path -Path $MiniforgeDir -ChildPath "condabin\mamba.bat" >> "%psFile%"
echo. >> "%psFile%"
echo Write-Output "Downloading the Miniforge installer from $RELEASE_URL" >> "%psFile%"
echo curl.exe -L -o $InstallerPath $RELEASE_URL >> "%psFile%"
echo if ($LASTEXITCODE -ne 0) { >> "%psFile%"
echo     Write-Output "ERROR: failed to download the Miniforge installer (exit code $LASTEXITCODE)." >> "%psFile%"
echo     pause >> "%psFile%"
echo     exit 1 >> "%psFile%"
echo } >> "%psFile%"
echo. >> "%psFile%"
echo Write-Output "`nInstalling Miniforge to $MiniforgeDir (this can take a minute)`n" >> "%psFile%"
echo ^# Standard silent-install flags for the NSIS-based Miniconda/Miniforge Windows installer. >> "%psFile%"
echo ^# /NoRegistry=1 asks it to skip the Add/Remove Programs entry in the first place -- this is >> "%psFile%"
echo ^# a documented constructor (the tool that builds these installers) option, but not every >> "%psFile%"
echo ^# installer build is guaranteed to honor it, so it is backed up by an explicit cleanup below. >> "%psFile%"
echo $InstallArgs = "/InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /NoRegistry=1 /S /D=$MiniforgeDir" >> "%psFile%"
echo $InstallProc = Start-Process -FilePath $InstallerPath -ArgumentList $InstallArgs -Wait -PassThru >> "%psFile%"
echo if ($InstallProc.ExitCode -ne 0 -or -not (Test-Path "$MambaBat")) { >> "%psFile%"
echo     Write-Output "ERROR: Miniforge installation did not complete successfully (exit code $($InstallProc.ExitCode))." >> "%psFile%"
echo     Write-Output "This can happen if antivirus/EDR software blocked the installer, or if a Miniforge install already exists at $MiniforgeDir." >> "%psFile%"
echo     pause >> "%psFile%"
echo     exit 1 >> "%psFile%"
echo } >> "%psFile%"
echo. >> "%psFile%"
echo ^# Best-effort cleanup of anything the installer may have left OUTSIDE $InstallDir, so that >> "%psFile%"
echo ^# deleting the cnapy-$InstallLabel folder later is a complete uninstall. Wrapped so a failure >> "%psFile%"
echo ^# here (e.g. restricted registry access) never aborts the install itself. >> "%psFile%"
echo try { >> "%psFile%"
echo     $UninstallRoot = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" >> "%psFile%"
echo     Get-ChildItem -Path $UninstallRoot -ErrorAction SilentlyContinue ^| ForEach-Object { >> "%psFile%"
echo         $Entry = Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue >> "%psFile%"
echo         if ($Entry -and $Entry.InstallLocation -and ($Entry.InstallLocation.TrimEnd('\') -eq $MiniforgeDir.TrimEnd('\'))) { >> "%psFile%"
echo             Remove-Item -Path $_.PSPath -Recurse -Force -ErrorAction SilentlyContinue >> "%psFile%"
echo         } >> "%psFile%"
echo     } >> "%psFile%"
echo } catch {} >> "%psFile%"
echo try { >> "%psFile%"
echo     ^# Default Start Menu folder name used by Miniforge installers; only removed if this >> "%psFile%"
echo     ^# specific install created it (Test-Path guards against removing a pre-existing one >> "%psFile%"
echo     ^# from an unrelated Miniforge/Miniconda install on the same machine). >> "%psFile%"
echo     $StartMenuDir = Join-Path -Path $Env:APPDATA -ChildPath "Microsoft\Windows\Start Menu\Programs\Miniforge3" >> "%psFile%"
echo     if (Test-Path $StartMenuDir) { >> "%psFile%"
echo         Remove-Item -Path $StartMenuDir -Recurse -Force -ErrorAction SilentlyContinue >> "%psFile%"
echo     } >> "%psFile%"
echo } catch {} >> "%psFile%"
echo. >> "%psFile%"
echo Invoke-WithRetry -Description "Creating the cnapy environment" -Action { ^& $MambaBat create -y -p "$EnvDir" python=3.10 pip openjdk -c conda-forge } >> "%psFile%"
echo if (-not (Test-Path "$PythonExe")) { >> "%psFile%"
echo     Write-Output "ERROR: environment creation did not produce a Python interpreter at $PythonExe." >> "%psFile%"
echo     Write-Output "This is usually caused by a network problem while downloading packages from conda-forge." >> "%psFile%"
echo     pause >> "%psFile%"
echo     exit 1 >> "%psFile%"
echo } >> "%psFile%"
echo. >> "%psFile%"
echo Invoke-WithRetry -Description "Installing uv" -Action { ^& "$PythonExe" -m pip install --no-cache-dir uv } >> "%psFile%"
if defined BRANCH (
    echo Invoke-WithRetry -Description "Installing cnapy" -Action { ^& "$PythonExe" -m uv --no-cache pip install --no-cache-dir "git+https://github.com/cnapy-org/CNApy.git@%BRANCH%" } >> "%psFile%"
) else (
    echo Invoke-WithRetry -Description "Installing cnapy" -Action { ^& "$PythonExe" -m uv --no-cache pip install --no-cache-dir cnapy } >> "%psFile%"
)
echo. >> "%psFile%"
echo ^# cnapy-environment is a self-contained conda environment: its own Scripts\cnapy.exe entry >> "%psFile%"
echo ^# point is launched directly, so miniforge3\ and conda/mamba are not needed again at runtime. >> "%psFile%"
echo $BatchFilePath = Join-Path -Path $InstallDir -ChildPath "RUN_CNApy.bat" >> "%psFile%"
echo $CnapyExe = Join-Path -Path $EnvDir -ChildPath "Scripts\cnapy.exe" >> "%psFile%"
echo $BatchFileContent = "@echo off`r`n`"$CnapyExe`"" >> "%psFile%"
echo Set-Content -Path $BatchFilePath -Value $BatchFileContent >> "%psFile%"
echo. >> "%psFile%"
echo ^# Create desktop icon using PowerShell >> "%psFile%"
echo $ShortcutPath = [System.IO.Path]::Combine($Env:USERPROFILE, "Desktop", "CNApy-$InstallLabel.lnk") >> "%psFile%"
echo $WScriptShell = New-Object -ComObject WScript.Shell >> "%psFile%"
echo $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath) >> "%psFile%"
echo $Shortcut.TargetPath = $BatchFilePath >> "%psFile%"
echo ^# $Shortcut.IconLocation = Join-Path -Path $ScriptDir -ChildPath "icon\CNApy_Icon.ico" >> "%psFile%"
echo $Shortcut.WorkingDirectory = $ScriptDir >> "%psFile%"
echo $Shortcut.Save() >> "%psFile%"
echo. >> "%psFile%"
echo Write-Output "`nDesktop shortcut created successfully`n" >> "%psFile%"

:: Ensure the PowerShell script file exists before running it
if exist "%psFile%" (
    :: Run the PowerShell script
    powershell -NoProfile -ExecutionPolicy Bypass -File "%psFile%"
    if %errorlevel% neq 0 (
        echo An error occurred while running the PowerShell script. CNApy was not installed correctly.
        echo If PowerShell was not found, install it on your device.
        del "%psFile%"
        pause
        exit /b 1
    )

    :: Delete the PowerShell script file
    del "%psFile%"

    :: Congratulate the user
    echo Congratulations! CNApy was successfully installed!
    echo To run CNApy, double-click on the newly created CNApy-%INSTALL_LABEL% desktop icon or,
    echo alternatively, double-click on the RUN_CNApy.bat file in the newly created cnapy-%INSTALL_LABEL% subfolder.
    echo To deinstall CNApy later, simply delete the newly created cnapy-%INSTALL_LABEL% subfolder.
    pause
) else (
    echo PowerShell script file not found: %psFile%
    echo Maybe your disk is full or you need to install CNApy in a folder where you allowed to write new files.
    echo This is because, often, folders such as the default Programs folder are restricted, so that other folders might work.
    echo Alternatively, you might need to run this installer with administrator priviledges!
    pause
)

endlocal
