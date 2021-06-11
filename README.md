# CNApy 

## *An integrated environment for metabolic model analysis*

![CNApy screenshot](screenshot.png)

## Install CNApy with conda

1. Create a conda environment with all dependencies
    ```sh
    conda create -n cnapy-0.0.6 -c conda-forge -c cnapy cnapy
    ```

2. Activate the cnapy conda environment
    ```
    conda activate cnapy-0.0.6
    ```

3. Run CNApy
    ```
    cnapy
    ```

**IMPORTANT**: To use the CNA Matlab functions you need atleast Matlab 2019b and the Python API for the Matlab engine installed and of course CNA. Alternatively to Matlab you can also use Octave.


## How to run a script in the CNApy terminal

```python
import testscript
testscript.run(cna)
```


## Setup the CNApy development environment with conda

We use conda as package manager to install all dependencies. You can use [miniconda](https://docs.conda.io/en/latest/miniconda.html).
If you have conda installed you can:

  conda env create -n cnapy -f environment.yml


1. Activate the cnapy conda environment
    ```
    conda activate cnapy
    ```

2. Checkout the latest cnapy development version using git
    ```   
    git clone https://github.com/cnapy-org/CNApy.git
    ```

3. Change into the source directory and install CNApy
    ```  
    cd CNApy
    ```

4. Run CNApy
    ```      
    python cnapy.py
    ```




## Contributing

[How to make a contribution to `CNApy`?](https://github.com/cnapy-org/CNApy/blob/master/CONTRIBUTING.md)

Any contribution intentionally submitted for inclusion in the work by you, shall be licensed under the terms of the Apache 2.0 license without any additional terms or conditions.
