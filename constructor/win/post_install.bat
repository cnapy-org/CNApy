call %~dp0..\Scripts\activate.bat

call mamba install cnapy -c cnapy -c conda-forge -v --yes
call pause
call %~dp0..\Scripts\conda clean --all --yes
project_downloader
