pip install --user cameo==0.13 cobra==0.18.1 qtconsole==4.7.7 --upgrade-strategy only-if-needed --ignore-installed ruamel_yaml
call %~dp0..\Scripts\activate.bat
call %~dp0..\Scripts\conda install cnapy -c arb-lab/label/test -c conda-forge -c bioconda --yes
