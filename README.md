![cnapy](./cnapylogo.svg "cnapy logo")
# cnapy - A CellNetAnalyzer GUI in Python


- create a conda environment for cnapy from the environment.yml

      conda env create -f environment.yml

- activate conda environment

      conda activate cnapy

- run cnapy

      python cnapy.py

## install matlab engine 2019b for python

- `cd /usr/local/net/MATLAB/R2019b/extern/engines/python`
- `python setup.py build --build-base="/scratch/mebuild" install`