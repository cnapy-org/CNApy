![CNApy main window](https://raw.githubusercontent.com/cnapy-org/CNApy/master/screenshot.png)

## CNApy installation with conda

We use conda as package manager to install CNApy. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).

1. Create a conda environment with all dependencies:
```
conda create -n cnapy-1.0.2 -c conda-forge -c cnapy cnapy=1.0.2
```
2. Activate the cnapy conda environment:
```
conda activate cnapy-1.0.2
```
3. Run CNApy
```
cnapy
```
IMPORTANT: To use the CNA Matlab functions you need at least [Matlab](https://www.mathworks.com) 2019b or [Octave](https://www.octave.org) 5.2. Also, you need to download [CellNetAnalyzer](http://www2.mpi-magdeburg.mpg.de/projects/cna/cna.html)

## Documentation

[CNApy guide](https://cnapy-org.github.io/CNApy-guide/)

Video tutorials

- [Create a new CNApy project](http://www.youtube.com/watch?v=bsNXZBmtyWw)
- [Perform FBA and FVA with CNApy](http://www.youtube.com/watch?v=I5RJjXRBRaQ)
- [Calculate Elementary Modes with CNApy](https://www.youtube.com/watch?v=AHyMk14_DxI)
- [Calculate Minimal Cut Sets with CNApy](https://www.youtube.com/watch?v=vFRdYI1ZQQM)

## How to run a script in the CNApy terminal

```python
import testscript
testscript.run(cna)
```

## Setup the CNApy development environment with conda

We use conda as package manager to install all dependencies. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html). If you have conda installed you can:
```
conda env create -n cnapy -f environment.yml
```
Activate the cnapy conda environment
```
conda activate cnapy
```
Checkout the latest cnapy development version using git
```
git clone https://github.com/cnapy-org/CNApy.git
```
Change into the source directory and install CNApy
```
cd CNApy
```
Run CNApy
```
python cnapy.py
```
## Contributing

[How to make a contribution to CNApy?](https://github.com/cnapy-org/CNApy/blob/master/CONTRIBUTING.md)

Any contribution intentionally submitted for inclusion in the work by you, shall be licensed under the terms of the Apache 2.0 license without any additional terms or conditions.
