# Create and upload a conda package

```sh
cd recipes/noarch
conda-build . -c conda-forge -c cnapy
anaconda login
anaconda upload -u cnapy FILENAME
```

# Create an windows installer with constructor

```sh
cd constructor/win
constructor .
```
