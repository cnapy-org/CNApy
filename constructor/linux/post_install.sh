#!/bin/sh
source $PREFIX/etc/profile.d/conda.sh
conda activate $PREFIX

conda install -v -c arb-lab/label/test -c conda-forge -c bioconda cnapy --yes
project_downloader