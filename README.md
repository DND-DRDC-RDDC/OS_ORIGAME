# ORIGAME
ORIGAME is a Python-based discrete event modelling and simulation environment.

It was jointly developed by Defence Research and Development Canada - Centre for Operational Research and Analysis (DRDC-CORA) and Director General Military Personnel Research and Analysis (DGMPRA).

(c) Her Majesty the King in Right of Canada

## LICENSE
See LICENSE file.

## RECOMMENDED INSTALLATION

These instructions are for running ORIGAME on python 3.11 

1. Install Python 3.11.2 (python-3.11.2-amd64.exe)
	- https://www.python.org/downloads/release/python-3112/

2. Install Visual C++ Redistributable for Visual Studio 2015 (vc_redist.x64.exe)
	- https://www.microsoft.com/en-ca/download/details.aspx?id=48145

3. Clone or download OS_ORIGAME to a project folder on your system

4. From the project folder, create a virtual environment for ORIGAME for each Python version
	- e.g. `C:\Python311\python -m venv venv11`

5. Activate the virtual environment and install dependencies in "requirements.txt". Deactivate the virtual environment
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

## CONTACT

Stephen Okazawa<br/>
Defence Scientist<br/>
Defence Research and Development Canada<br/>
stephen.okazawa@forces.gc.ca<br/>

