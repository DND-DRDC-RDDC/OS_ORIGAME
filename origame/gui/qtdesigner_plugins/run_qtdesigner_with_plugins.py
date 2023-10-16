# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
Script to start Qt Designer with plugins from Origame.

Note: The PyQt5 wheel from pypi no longer includes developer tools like Designer. These tools have
to be installed by installing the Qt C++ binary distribution.
"""

# -- Imports ------------------------------------------------------------------------------------

from pathlib import Path
import os
import sys

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Script -------------------------------------------------------------------------------------

base = Path(__file__).parent.resolve()
os.environ['PYQTDESIGNERPATH'] = str(base)
origame_path = str(base.parent.parent.parent)
os.environ['PYTHONPATH'] = origame_path

import PyQt5

qt_dir = str(Path(PyQt5.__file__).parent)
command = r"C:\Qt\Qt5.7.0\5.7\msvc2015_64\bin\designer.exe {}".format(sys.argv[1])

print('plugins in', os.getenv('PYQTDESIGNERPATH'))
print('origame in', origame_path)
print('command to run', command)

os.system(command)
