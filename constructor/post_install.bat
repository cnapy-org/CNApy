call %~dp0..\Scripts\activate.bat
call %~dp0..\Scripts\conda install cnapy -c arb-lab/label/test -c conda-forge -c bioconda --yes
pip install --user cameo --upgrade-strategy only-if-needed
project-downloader
