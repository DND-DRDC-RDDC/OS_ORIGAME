# ORIGAME
Private repository for ORIGAME simulation software.

This repository was created for a Government of Canada contract to update the ORIGAME code base.

(c) Her Majesty the Queen in Right of Canada

## LICENSE
See LICENSE file.

## RECOMMENDED INSTALLATION

These instructions are for running ORIGAME on python 3.8 and 3.11 

1. Install Python 3.8.10 (python-3.8.10-amd64.exe)
	- https://www.python.org/downloads/release/python-3810/

2. Install Python 3.11.2 (python-3.11.2-amd64.exe)
	- https://www.python.org/downloads/release/python-3112/

3. Install Visual C++ Redistributable for Visual Studio 2015 (vc_redist.x64.exe)
	- https://www.microsoft.com/en-ca/download/details.aspx?id=48145

4. Clone or download ORIGAME to a project folder on your system

5. From the project folder, create a virtual environment for ORIGAME for each Python version
	- e.g. `C:\Python38\python -m venv venv8`
	- e.g. `C:\Python311\python -m venv venv11`

6. Activate a virtual environment and install dependencies in "requirements.txt". Deactivate the virtual environment
if not in use.
	- `venv11\Scripts\activate`
	- `pip install -r requirements.txt`
	- `deactivate`

7. Activate the desired virtual environment, and launch ORIGAME GUI.
	- `venv11\Scripts\activate`
	- `py .\origame_gui.py`

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

## CONTACT

Stephen Okazawa<br/>
Defence Scientist<br/>
Defence Research and Development Canada<br/>
stephen.okazawa@forces.gc.ca<br/>

