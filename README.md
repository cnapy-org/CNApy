# CNApy

## *An integrated environment for metabolic network analysis*

![CNApy screenshot](screenshot.png)


## Downloads

- The latest release can be found on the [release page](https://github.com/cnapy-org/CNApy/releases/latest)

- The [CNApy guide](https://cnapy-org.github.io/CNApy-guide/)

- Example projects [CNApy projects](https://github.com/cnapy-org/CNApy-projects/releases/latest)

## Video tutorials

You can find several video tutorials on our [CNApy YouTube channel](https://www.youtube.com/channel/UCRIXSdzs5WnBE3_uukuNMlg).

## Install CNApy with conda

We use conda as package manager to install CNApy. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).

0. (only recommended if you have already installed CNApy by using conda) If you already have a cnapy environment, e.g., cnapy-1.X.X, you can delete it with the command
    ```sh
    # Here, the Xs stand for the last CNApy version you've installed by using conda
    conda env remove -n cnapy-1.X.X
    ```
1. (optional, but recommended if you also use other Python distributions or Anaconda environments) In order to solve
   potential package version problems, set a systems variable called "PYTHONNOUSERSITE" to the value "True".

   Under Linux systems, you can do this with the following command:
   ```sh
   export PYTHONNOUSERSITE=True
   ```

   Under Windows systems, you can do this by searching for your system's "environmental variables" and adding
   the variable PYTHONNOUSERSITE with the value True using Window's environmental variables setting window.

2. Create a conda environment with all dependencies
    ```sh
    conda create -n cnapy-1.0.5 -c conda-forge -c cnapy cnapy=1.0.5
    ```

3. Activate the cnapy conda environment
    ```sh
    conda activate cnapy-1.0.5
    ```

4. Run CNApy
    ```sh
    cnapy
    ```

**IMPORTANT**: To use the CellNetAnalyzer (CNA) Matlab functions you need atleast Matlab 2019b and the Python API for the Matlab engine installed and of course [CellNetAnalyzer itself](https://www2.mpi-magdeburg.mpg.de/projects/cna/cna.html). Alternatively to Matlab you can also use the free and open-source [GNU Octave](https://www.gnu.org/software/octave/index).

## How to run a script in the CNApy terminal

A toy example is included in this repository [here](https://github.com/cnapy-org/CNApy/blob/master/testscript.py).
You can execute the script from the CNApy console like this.

```python
import testscript
testscript.run(cna)
```

## Contributing

[How to make a contribution to `CNApy`?](https://github.com/cnapy-org/CNApy/blob/master/CONTRIBUTING.md)

Any contribution intentionally submitted for inclusion in the work by you, shall be licensed under the terms of the Apache 2.0 license without any additional terms or conditions.

## Setup the CNApy development environment with conda

We use conda as package manager to install all dependencies. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).
If you have conda installed you can:


1. Create a conda devlopment environment with all dependencies
    ```
    conda env create -n cnapy-dev -f environment.yml
    ```

2. Activate the development environment
    ```
    conda activate cnapy-dev
    ```

2. Checkout the latest cnapy development version using git
    ```
    git clone https://github.com/cnapy-org/CNApy.git
    ```

3. Change into the source directory and run CNApy
    ```
    cd CNApy
    python cnapy.py
    ```
Any contribution intentionally submitted for inclusion in the work by you, shall be licensed under the terms of the Apache 2.0 license without any additional terms or conditions.
