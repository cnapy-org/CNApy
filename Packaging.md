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
# You have to create a noarch package for all systems except
# Windows and a win64 package for Windows. Otherwise, without
# a specific win64 package, the Windows .exe installer will not
# work.
conda config --add channels IBMDecisionOptimization
conda config --add channels Gurobi
conda config --add channels conda-forge

cd recipes/noarch
conda-build . -c conda-forge -c cnapy
anaconda login
anaconda upload -u cnapy FILENAME

cd ..
cd win
conda-build . -c conda-forge -c cnapy
anaconda login
anaconda upload -u cnapy FILENAME
```

# Create an windows installer with constructor

```sh
cd constructor/win
constructor .
```
