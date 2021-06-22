under construction
{:toc}
![CNApy main window](https://raw.githubusercontent.com/cnapy-org/CNApy/master/screenshot.png)

## CNApy installation with conda

1. Create a conda environment with all dependencies:
```
conda create -n cnapy-0.0.6 -c conda-forge -c cnapy cnapy
```
2. Activate the cnapy conda environment:
```
conda activate cnapy-0.0.6:
```
3. Run CNApy
```
cnapy
```
IMPORTANT: To use the CNA Matlab functions you need at least [Matlab](https://www.mathworks.com) 2019b or [Octave](https://www.octave.org) 5.2. Also, you need to download [CellNetAnalyzer](http://www2.mpi-magdeburg.mpg.de/projects/cna/cna.html)

## Documentation

[CNApy manual](CNApyUsersGuide.html)

Video tutorials

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

Delete stuff below later
--------------------

## Welcome to GitHub Pages

You can use the [editor on GitHub](https://github.com/cnapy-org/CNApy/edit/gh-pages/index.md) to maintain and preview the content for your website in Markdown files.

Whenever you commit to this repository, GitHub Pages will run [Jekyll](https://jekyllrb.com/) to rebuild the pages in your site, from the content in your Markdown files.
### Markdown

Markdown is a lightweight and easy-to-use syntax for styling your writing. It includes conventions for

```markdown
Syntax highlighted code block

# Header 1
## Header 2
### Header 3

- Bulleted
- List

1. Numbered
2. List

**Bold** and _Italic_ and `Code` text

[Link](url) and ![CNApy main window](https://raw.githubusercontent.com/cnapy-org/CNApy/master/screenshot.png)
```

For more details see [GitHub Flavored Markdown](https://guides.github.com/features/mastering-markdown/).

### Jekyll Themes

Your Pages site will use the layout and styles from the Jekyll theme you have selected in your [repository settings](https://github.com/cnapy-org/CNApy/settings/pages). The name of this theme is saved in the Jekyll `_config.yml` configuration file.

### Support or Contact

Having trouble with Pages? Check out our [documentation](https://docs.github.com/categories/github-pages-basics/) or [contact support](https://support.github.com/contact) and we’ll help you sort it out.
