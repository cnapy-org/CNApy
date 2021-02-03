# CNApy - A CellNetAnalyzer GUI in Python

IMPORTANT: To use the CNA MATLAB functions you need atleast MATLAB 2019b and the Python API for the MATLAB engine installed and of course CNA

## Install Python API for MATLAB engine in MATLAB 2019b

First activate the cnapy conda environment

  conda activate cnapy

then

```sh
cd /usr/local/net/MATLAB/R2019b/extern/engines/python
python setup.py build --build-base="/scratch/mebuild" install
```

## Set CNA path

To use the CNA MATLAB functions you need to tell CNApy where CNA is installed.
Therefore, open or create a file `cnapy-config.txt` with the following content (change the path to your CNA path).

```txt
[cnapy-config]
cna_path = /my_folder/CellNetAnalyzer/
```

## How to run a script in the cnapy terminal

```python
import testscript
testscript.work(cna)
```
