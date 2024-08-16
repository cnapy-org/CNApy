# CNApy

## *An integrated environment for metabolic network analysis*

![CNApy screenshot](screenshot.png)


## Downloads

- The latest release can be found on the [release page](https://github.com/cnapy-org/CNApy/releases/latest)

- The [CNApy user guide](https://cnapy-org.github.io/CNApy/CNApyUsersGuide.html)

- Example projects [CNApy projects](https://github.com/cnapy-org/CNApy-projects/releases/latest)

## Video tutorials

- [Create a new CNApy project](http://www.youtube.com/watch?v=bsNXZBmtyWw)
- [Perform FBA and FVA with CNApy](http://www.youtube.com/watch?v=I5RJjXRBRaQ)

## Install CNApy with conda

We use conda as package manager to install CNApy. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).

1. Create a conda environment with all dependencies
    ```sh
    conda create -n cnapy-1.2.1 -c conda-forge -c cnapy cnapy=1.2.1
    ```

2. Activate the cnapy conda environment
    ```
    conda activate cnapy-1.2.1
    ```

3. Run CNApy
    ```
    cnapy
    ```


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
