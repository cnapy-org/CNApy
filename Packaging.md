# Packaging

# First: Change the version number

An easy way to do this in VS Code is to replace the current version number
(which you can deduce from the current release) by replacing the version
number globally with your desired new value. If there are any now undesired
additions such as beta, rc1 etc. you should remove them now.

# Prerequisites

```sh
conda install conda-build
conda install anaconda-client
conda install constructor
````

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
