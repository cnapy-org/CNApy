#!/bin/sh
source $PREFIX/etc/profile.d/conda.sh
conda activate $PREFIX

conda install -v -c cnapy -c conda-forge --yes
conda clean --all --yes