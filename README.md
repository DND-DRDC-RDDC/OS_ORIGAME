# ORIGAME
ORIGAME (Operational Research Integrated Graphical Analysis and Modelling Environment - pronounced "o-ri-ga-mee") is a Python-based discrete event modelling and simulation environment. Model events and data are defind using Python functions and data structures, and a graphical user interface allows users to interconnect model components, run Monte Carlo simulations, and analyze results.

The project is released under Open Science (OS), an initiative of the Government of Canada to make the research products of federal scientists open to the public.

(c) His Majesty the King in Right of Canada

## LICENSE
See LICENSE file.

## RECOMMENDED INSTALLATION

These instructions are for running ORIGAME on Python 3.8 and 3.11

1. Install the most recent Python 3.8 and/or Python 3.11 release for your system
	- https://www.python.org/downloads/windows/

2. Install Visual C++ Redistributable for Visual Studio 2015 (vc_redist.x64.exe)
	- https://www.microsoft.com/en-ca/download/details.aspx?id=48145

3. Clone or download ORIGAME to a project folder on your system

4. From the project folder, create a virtual environment for ORIGAME for each Python version that you wish to run
   ORIGAME within
	- e.g. `C:\Python38\python -m venv venv8`
	- e.g. `C:\Python311\python -m venv venv11`

5. Activate a virtual environment and install dependencies in "requirements.txt". Deactivate the virtual environment
   if not in use. For example, with Python 11, run:
	- `venv11\Scripts\activate`
	- `pip install -r requirements.txt`
	- `deactivate`

6. Activate the desired virtual environment, and launch ORIGAME GUI.
	- `venv11\Scripts\activate`
	- `python .\origame_gui.py`

Visit this [this page](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#activating-a-virtual-environment) for more information about virtual environments.

## DOCUMENTATION

The ORIGAME User Manual and ORIGAME Tutorial documents are located in the /origame/docs folder.

## BACKWARDS COMPATIBILITY

The current version of ORIGAME requires Pandas 2.0 or higher, which can cause older scenarios to fail to load
if they require Pandas 1.x. The load error associated with this problem can be seen in the following image:

![Pandas 1 Required](wiki_images\pandas_1_required.png)

To resolve this issue, run the following command in your virtual environment before launching ORIGAME:
`pip install pandas==1.5.3`

## TESTING

A number of test scenarios and run procedures are provided in the /testing folder.

These test scenarios constitute Government Supplied Material 2 (GSM 2), referred to in the task Statement of Work.

Note: **Pandas 1.5.3** is required for loading and running Scenario 2 that is provided in the /testing folder, so make sure
it is installed in the python virtual environment before launching ORIGAME, by running the command in the
Backwards Compatibility section of this document.

## UI Changes

After making changes to the ui components (The .ui files, and .qrc files), or adding new ones, it is imperative to run
the script to compile them to python code. To do this run:

``` pwsh
python .\origame\gui\compile_all_ui_files.py
```

This should also be done if updating QT dependencies.

Note that the above relies on the requirements_update_gui.txt being installed first:

``` pwsh
pip install -r requirements_update_gui.txt
```

## CONTACT

Stephen Okazawa<br/>
Defence Scientist<br/>
Defence Research and Development Canada<br/>
stephen.okazawa@forces.gc.ca<br/>

