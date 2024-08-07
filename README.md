# ORIGAME
ORIGAME (Operational Research Integrated Graphical Analysis and Modelling Environment - pronounced "o-ri-ga-mee") is a Python-based discrete event modelling and simulation environment. Model events and data are defind using Python functions and data structures, and a graphical user interface allows users to interconnect model components, run Monte Carlo simulations, and analyze results.

The project is released under Open Science (OS), an initiative of the Government of Canada to make the research products of federal scientists open to the public. ORIGAME was jointly developed by two research organizations within the Canadian Department of National Defence: Defence Research and Development Canada - Centre for Operational Research and Analysis (DRDC-CORA) and Director General Military Personnel Research and Analysis (DGMPRA).




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
	- e.g. `C:\Python311\python -m venv venv`

5. Activate the virtual environment and install dependencies in "requirements.txt". Deactivate the virtual environment
if not in use.
	- `venv\Scripts\activate`
	- `pip install -r requirements.txt`
	- `deactivate`

7. Activate the desired virtual environment, and launch ORIGAME GUI.
	- `venv\Scripts\activate`
	- `py .\origame_gui.py`

Visit this [this page](https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/#activating-a-virtual-environment) for more information about virtual environments.

## DOCUMENTATION

The ORIGAME User Manual and ORIGAME Tutorial documents are located in the /origame/docs folder.

## CONTACT

Stephen Okazawa<br/>
Defence Scientist<br/>
Defence Research and Development Canada<br/>
stephen.okazawa@forces.gc.ca<br/>

