# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
used to compile all ui files present in origame
"""

# -- Imports ------------------------------------------------------------------------------------

import glob
import os
import subprocess
from pathlib import Path
from PyQt6.uic import compileUi

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Script -------------------------------------------------------------------------------------

def main():
    ui_files = glob.glob('**/ui_files/*.ui', root_dir='.', recursive=True)
    for file in ui_files:
        in_dir: Path = Path(file).parent
        out_dir: Path = in_dir.parent
        out_file = os.path.join(str(out_dir), f"Ui_{Path(file).stem}.py")
        print('Compiling {} to {}'.format(file, out_file))
        with open(out_file, "w") as fp:
            compileUi(file, fp)
    qrc_files = glob.glob('**/ui_files/*.qrc', root_dir='.', recursive=True)
    for file in qrc_files:
        in_dir: Path = Path(file).parent
        out_dir: Path = in_dir.parent
        out_file = os.path.join(str(out_dir), f"{Path(file).stem}_rc.py")
        print('Compiling {} to {}'.format(file, out_file))
        try:
            result = subprocess.run(['pyside6-rcc', file], capture_output=True, text=True)
            if result.returncode != 0:
                print("Error:")
                print(result.stderr)
                print("")
                print("Have you ran:")
                print("    pip install -r requirements_update_gui.txt")
                exit(-1)
            else:
                old_qrc_code = result.stdout
                new_qrc_code = old_qrc_code.replace("PySide6", "PyQt6")
                with open(out_file, "w") as fp:
                    fp.write(new_qrc_code)
        except Exception as exc:
            print("Error:")
            print(f"{exc}")
            print("Have you ran:")
            print("    pip install -r requirements_update_gui.txt")
            exit(-2)

if __name__ == "__main__":
    print("Note that this script relies on contents of requirements_update_gui.txt to be installed")
    main()