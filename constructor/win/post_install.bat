call %~dp0..\Scripts\activate.bat
call %~dp0..\Scripts\conda install cnapy -c cnapy -c conda-forge --yes
call %~dp0..\Scripts\conda clean --all --yes
project_downloader
