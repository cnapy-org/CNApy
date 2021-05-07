call %~dp0..\Scripts\activate.bat
@REM @REM call %~dp0..\Scripts\conda config --set unsatisfiable_hints True
@REM call %~dp0..\Scripts\conda config --set remote_read_timeout_secs 120
@REM call %~dp0..\Scripts\conda config --set remote_connect_timeout_secs: 60
@REM call mamba install optlang_enumerator -c cnapy -c conda-forge -v --yes
@REM @REM call pause
@REM call mamba install cnapy -c cnapy -c conda-forge -v --yes
@REM call pause
call %~dp0..\Scripts\conda clean --all --yes
project_downloader
