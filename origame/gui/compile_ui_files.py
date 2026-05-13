# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
Script for pyuic to compile all .ui files to Python source in parent folder of current working dir. Based on
script of same name in Eric IDE source.
"""

# -- Imports ------------------------------------------------------------------------------------

import sys
from pathlib import Path

from PyQt5.uic import compileUiDir, compileUi

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Script -------------------------------------------------------------------------------------

print('Working folder is', Path.cwd())


def main(argv):
    in_dir = argv[1]
    out_dir = '.'  # str(Path(in_dir).parent)

    if Path(in_dir).is_dir():
        # assumes current working dir is parent of in_dir:

        def py_name(py_dir, py_file):
            name_info = out_dir, "Ui_{0}".format(py_file)
            print('  ', '\\'.join(name_info))
            return name_info

        print('Will compile all .ui files in {} to {}:'.format(in_dir, out_dir))
        compileUiDir(str(in_dir), recurse=True, map=py_name, from_imports=True)

    else:
        in_dir = Path(argv[2]) / in_dir
        print('Will compile {} file to {}'.format(in_dir, out_dir))
        with Path(r"{}\Ui_{}.py".format(out_dir, Path(in_dir).stem)).open('w') as pyfile:
            compileUi(str(in_dir), pyfile, from_imports=True)


if __name__ == "__main__":
    main(sys.argv)
