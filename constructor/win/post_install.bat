call %~dp0..\Scripts\activate.bat
call %~dp0..\Scripts\conda install cnapy -c cnapy/label/test -c conda-forge -c bioconda --yes
call %~dp0..\Scripts\conda clean --all --yes
pip install --user cameo --upgrade-strategy only-if-needed
project_downloader
