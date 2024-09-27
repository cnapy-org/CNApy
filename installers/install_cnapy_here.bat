@echo off
setlocal

:: Set the PowerShell script file name
set "psFile=install_cnapy.ps1"

:: Write the PowerShell script to a file
echo # Adapted from https://raw.githubusercontent.com/mamba-org/micromamba-releases/main/install.ps1 > "%psFile%"
echo. >> "%psFile%"
echo $CNAPY_VERSION = "1.2.2"  ^# Replace with the actual version if needed >> "%psFile%"
echo $RELEASE_URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64" >> "%psFile%"
echo. >> "%psFile%"
echo Write-Output "Downloading micromamba from $RELEASE_URL" >> "%psFile%"
echo curl.exe -L -o micromamba.exe $RELEASE_URL >> "%psFile%"
echo. >> "%psFile%"
echo ^# Get the directory where the script is located >> "%psFile%"
echo $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path >> "%psFile%"
echo. >> "%psFile%"
echo $InstallDir = Join-Path -Path $ScriptDir -ChildPath "cnapy-$CNAPY_VERSION" >> "%psFile%"
echo New-Item -ItemType Directory -Force -Path $InstallDir ^| out-null >> "%psFile%"
echo. >> "%psFile%"
echo $MAMBA_INSTALL_PATH = Join-Path -Path $InstallDir -ChildPath "micromamba.exe" >> "%psFile%"
echo. >> "%psFile%"
echo Write-Output "`nInstalling micromamba to $InstallDir`n" >> "%psFile%"
echo Move-Item -Force micromamba.exe $MAMBA_INSTALL_PATH ^| out-null >> "%psFile%"
echo. >> "%psFile%"
echo ^# Use ^& to execute the micromamba commands stored in the variable >> "%psFile%"
echo ^& $MAMBA_INSTALL_PATH create -y -p "./cnapy-$CNAPY_VERSION/cnapy-environment" python=3.10 pip openjdk -r "./cnapy-$CNAPY_VERSION/" -c conda-forge >> "%psFile%"
echo Copy-Item -Path "cnapy-1.2.2/condabin/mamba.bat" -Destination "cnapy-1.2.2/condabin/micromamba.bat" >> "%psFile%"
echo ^& $MAMBA_INSTALL_PATH run -p "./cnapy-$CNAPY_VERSION/cnapy-environment" -r "./cnapy-$CNAPY_VERSION/" pip install --no-cache-dir uv >> "%psFile%"
echo ^& $MAMBA_INSTALL_PATH run -p "./cnapy-$CNAPY_VERSION/cnapy-environment" -r "./cnapy-$CNAPY_VERSION/" uv --no-cache pip install --no-cache-dir cnapy >> "%psFile%"
echo. >> "%psFile%"
echo ^# Create a new PowerShell file called "cnapy_runner_helper.ps1" >> "%psFile%"
echo $PsFilePath = Join-Path -Path $InstallDir -ChildPath "cnapy_runner_helper.ps1" >> "%psFile%"
echo $PsFileContent = "$MAMBA_INSTALL_PATH run -p `"$InstallDir\cnapy-environment`" -r `"$InstallDir\`" cnapy" >> "%psFile%"
echo Set-Content -Path $PsFilePath -Value $PsFileContent >> "%psFile%"
echo. >> "%psFile%"
echo ^# Create a new batch file called "RUN_CNApy.bat" >> "%psFile%"
echo $BatchFilePath = Join-Path -Path $InstallDir -ChildPath "RUN_CNApy.bat" >> "%psFile%"
echo $BatchFileContent = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\cnapy_runner_helper.ps1`"" >> "%psFile%"
echo Set-Content -Path $BatchFilePath -Value $BatchFileContent >> "%psFile%"
echo. >> "%psFile%"
echo ^# Create desktop icon using PowerShell >> "%psFile%"
echo $ShortcutPath = [System.IO.Path]::Combine($Env:USERPROFILE, "Desktop", "CNApy-$CNAPY_VERSION.lnk") >> "%psFile%"
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
    echo To run CNApy, double-click on the newly created CNApy-1.2.2 desktop icon or,
    echo alternatively, double-click on the RUN_CNApy.bat file in the newly created cnapy-1.2.2 subfolder.
    echo To deinstall CNApy later, simply delete the newly created cnapy-1.2.2 subfolder.
    pause
) else (
    echo PowerShell script file not found: %psFile%
    echo Maybe your disk is full or you need to install CNApy in a folder where you allowed to write new files.
    echo This is because, often, folders such as the default Programs folder are restricted, so that other folders might work.
    echo Alternatively, you might need to run this installer with administrator priviledges!
    pause
)

endlocal
