call %~dp0..\Scripts\activate.bat

call mamba install cnapy=1.1.4 -c cnapy -c conda-forge -v --yes
call pause
call %~dp0..\Scripts\conda clean --all --yes
