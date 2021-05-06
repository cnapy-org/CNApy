# Create and upload a conda package

```sh
cd recipes/linux
conda-build . -c conda-forge
anaconda login
anaconda upload -u cnapy -l test FILENAME
```

# Create an installer with constructor

```sh
cd constructor/win
constructor .
```
