# Create and upload a conda package

```sh
cd recipes/linux
conda-build . -c conda-forge -c bioconda
anaconda login
anaconda upload -u cnapy -l test FILENAME
```

# Create an installer with constructor

```sh
cd constructor/win
constructor .
```
