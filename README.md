# CNApy - An integrated environment for metabolic modeling

[![Latest stable release](https://flat.badgen.net/github/release/cnapy-org/cnapy/stable)](https://github.com/cnapy-org/CNApy/releases/latest)
[![Last commit](https://flat.badgen.net/github/last-commit/cnapy-org/cnapy)](https://github.com/cnapy-org/CNApy/commits/master)
[![Open issues](https://flat.badgen.net/github/open-issues/cnapy-org/cnapy)](https://github.com/cnapy-org/CNApy/issues)
[![Gitter chat](https://flat.badgen.net/gitter/members/cnapy-org/community)](https://gitter.im/cnapy-org/community)

![CNApy screenshot](screenshot.png)

## Introduction

**If you have questions or suggestions regarding CNApy, you can use either of the [CNApy GitHub issues](https://github.com/cnapy-org/CNApy/issues), the [CNApy GitHub discussions](https://github.com/cnapy-org/CNApy/discussions) or the [CNApy Gitter chat room](https://gitter.im/cnapy-org/community).**

CNApy is a Python-based graphical user interface for a) many common methods of Constraint-Based Reconstruction and Analysis (COBRA) with stoichiometric metabolic models, b) the visualization of COBRA calculation results and c) the creation and editing of metabolic models.

Supported COBRA methods include Flux Balance Analysis (FBA), Flux Variability Analysis (FVA), Minimal Cut Sets (MCS), Elementary Flux Modes (EFM) and many more advanced strain design algorithms through its integration of the [StrainDesign](https://github.com/klamt-lab/straindesign) package.

All calculation results can be visualized in CNApy's interactive metabolic maps, which can be directly edited by the user. [Escher maps](https://escher.github.io/#/) are also natively supported and can be created and edited inside CNApy.

Aside of performing calculations on metabolic models, CNApy can also be used to create and/or edit metabolic models, including all important aspects of the model's reactions, metabolites and genes. CNApy supports the widely used [SBML standard format](https://sbml.org/) for model loading and export.

**For more details on CNApy's many more features, see section [Documentation and Tutorials](#documentation-and-tutorials).**

**For information about how to install CNApy, see section [Installation Options](#installation-options).**

**For information about how to contribute to CNApy as a developer, see section [Contribute to the CNApy development](#contribute-to-the-cnapy-development).**

**If you want to cite CNApy, see section [How to cite CNApy](#how-to-cite-cnapy).**

*Associated project note*: If you want to use the well-known MATLAB-based *CellNetAnalyzer* (CNA), *which is not compatible with CNApy*, you can download it from [CNA's website](https://www2.mpi-magdeburg.mpg.de/projects/cna/cna.html).

## Documentation and Tutorials

* The [CNApy guide](https://cnapy-org.github.io/CNApy-guide/) contains information for all major functions of CNApy.
* Our [CNApy YouTube channel](https://www.youtube.com/channel/UCRIXSdzs5WnBE3_uukuNMlg) provides some videos of working with CNApy.
* We also provide directly usable [CNApy example projects](https://github.com/cnapy-org/CNApy-projects/releases/latest) which include some of the most common *E. coli* models. These projects can also be downloaded within CNApy at its first start-up or via CNApy's File menu.

## Installation Options

There are three ways to install CNApy:

1. As the easiest installation way which only works under Windows, you can use the .exe installer attached to the assets at the bottom of [CNApy's latest release](https://github.com/cnapy-org/CNApy/releases/latest).
2. Under any operating system, you can install CNApy as a conda package as described in section [Install CNApy as conda package](#install-cnapy-as-conda-package).
3. If you want to develop CNApy, follow the instruction for the successful cloning of CNApy in section [Setup the CNApy development environment](#setup-the-cnapy-development-environment).

## Contribute to the CNApy development

Everyone is welcome to contribute to CNApy's development. [See our contribution file for more detailed instructions](https://github.com/cnapy-org/CNApy/blob/master/CONTRIBUTING.md).

## Install CNApy as conda package

1. We use conda as package manager to install CNApy, so that, if not already done yet, you have to install either the full-fledged [Anaconda](https://www.anaconda.com/) or the smaller [miniconda](https://docs.conda.io/en/latest/miniconda.html) conda installern on your system.

2. Add the additional channels used by CNApy to conda:

    ```sh
    conda config --add channels IBMDecisionOptimization
    conda config --add channels Gurobi
    ```

3. Create a conda environment with all dependencies

    ```sh
    conda create -n cnapy-1.1.6 -c conda-forge -c cnapy cnapy=1.1.6
    ```

4. Activate the cnapy conda environment

    ```sh
    conda activate cnapy-1.1.6
    ```

5. Run CNApy within you activated conda environment

    ```sh
    cnapy
    ```

Furthermore, you can also perform the following optional steps:

6. (optional and only recommended if you have already installed CNApy by using conda) If you already have a cnapy environment, e.g., cnapy-1.X.X, you can delete it with the command

    ```sh
    # Here, the Xs stand for the last CNApy version you've installed by using conda
    conda env remove -n cnapy-1.X.X
    ```

7. (optional, but recommended if you also use other Python distributions or Anaconda environments) In order to solve potential package version problems, set a systems variable called "PYTHONNOUSERSITE" to the value "True".

   Under Linux systems, you can do this with the following command:

   ```sh
   export PYTHONNOUSERSITE=True
   ```

   Under Windows systems, you can do this by searching for your system's "environmental variables" and adding
   the variable PYTHONNOUSERSITE with the value True using Window's environmental variables setting window.

## Setup the CNApy development environment

We use conda as package manager to install all dependencies. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).
If you have conda installed you can:

1. Create a conda development environment with all dependencies

    ```sh
    conda env create -n cnapy-dev -f environment.yml
    ```

2. Activate the development environment

    ```sh
    conda activate cnapy-dev
    ```

3. Checkout the latest cnapy development version using git

    ```sh
    git clone https://github.com/cnapy-org/CNApy.git
    ```

4. Change into the source directory and run CNApy

    ```sh
    cd CNApy
    python cnapy.py
    ```

Any contribution intentionally submitted for inclusion in the work by you, shall be licensed under the terms of the Apache 2.0 license without any additional terms or conditions.

## How to cite CNApy

If you use CNApy in your scientific work, please consider to cite CNApy's publication:

Thiele et al. (2022). CNApy: a CellNetAnalyzer GUI in Python for analyzing and designing metabolic networks.
*Bioinformatics* 38, 1467-1469, [doi.org/10.1093/bioinformatics/btab828](https://doi.org/10.1093/bioinformatics/btab828).
