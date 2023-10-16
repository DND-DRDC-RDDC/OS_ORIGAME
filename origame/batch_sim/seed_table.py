# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module exposes functions that can be used to read/write to a seed file.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import csv
import logging
from random import Random
from pathlib import Path

# [2. third-party]

# [3. local]
from ..core.typing import AnnotationDeclarations
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..scenario.sim_controller import MIN_RAND_SEED, MAX_RAND_SEED, MIN_VARIANT_ID, MIN_REPLIC_ID

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'SeedFileFormatError',
    'SeedFileIncompleteError',
    'SeedFileInvalidInformationError',
    'SeedTable',
    'MIN_VARIANT_ID',
    'MIN_REPLIC_ID',
]

log = logging.getLogger('system')

LINE_OFFSET = 1  # Offset to account for CSV file header line


class Decl(AnnotationDeclarations):
    SeedTable = 'SeedTable'


# -- Class Definitions --------------------------------------------------------------------------

class SeedFileFormatError(Exception):
    """Raised when a seed file is being read has wrong format"""

    def __init__(self, msg):
        super().__init__(msg)


class SeedFileIncompleteError(Exception):
    def __init__(self, variant_id, num_missing):
        super().__init__("Missing seeds for desired seed table", variant_id, num_missing)


class SeedFileInvalidInformationError(Exception):
    """Raised when the format is correct but the info is invalid, such as a value not being within allowed range. """

    def __init__(self, msg):
        super().__init__(msg)


class SeedTable:
    """
    Represent the random seeds to be used for a batch simulation of N variants by M replications per variant.
    The table can be saved to file in CSV format, and loaded from CSV.

    The CSV file must be in the format 'variant, replication, seed' with a header 'var,rep,seed'.
    An example of a valid csv file that can be loaded by this class is:

    var,rep,seed
    1,1,454
    1,2,399
    2,1,09923
    2,2,876
    3,1,56373
    3,2,09955
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SeedList = List[Tuple[int, int, float]]

    VARIANT_COL = 0
    REPLIC_COL = 1
    SEED_COL = 2

    _csv_header = ('var', 'rep', 'seed')

    # --------------------------- class-wide methods --------------------------------------------

    @staticmethod
    def from_list(seed_list: SeedList) -> Decl.SeedTable:
        """Converts a list of seeds to a SeedTable object"""

        num_variants = seed_list[-1][0]
        num_replics_per_variant = seed_list[-1][1]
        seed_table = SeedTable(num_variants, num_replics_per_variant)

        for variant_id, replic_id, seed in seed_list:
            seed_table.set_seed(variant_id, replic_id, seed)

        return seed_table

    @staticmethod
    def get_csv_file_name(filename: PathType):
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".csv")

        if path.suffix != ".csv":
            raise ValueError("Filename '{}' has invalid suffix, must be .csv".format(filename))

        return path

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, num_variants: int, num_replics_per_variant: int, csv_path: PathType = None):
        """
        If no path given, then random numbers will be generated for given number of variants and replics per variant.
        Otherwise, the file must contain random seeds for the specified number of variants and replics per variant.

        :param num_variants:  The number of variants expected in the seed file
        :param num_replics_per_variant:  The number of replications per num_variants expected in the seed file
        :param csv_path:  If given, file to load seeds from.
        """

        self._num_variants = num_variants
        self._replics_per_variant = num_replics_per_variant
        self._seeds = self._generate_seeds()
        self._csv_path = None
        if csv_path:
            self._csv_path = self.get_csv_file_name(csv_path)

    def get_seeds_list_iter(self) -> Iterable[Tuple[int, int, int]]:
        """
        Get a copy of the 2d array (list of list) representation of a seed file.
        """
        for variant_id, variant_seeds in enumerate(self._seeds):
            if variant_id >= MIN_VARIANT_ID:
                for replic_id, seed in enumerate(variant_seeds):
                    if replic_id >= MIN_REPLIC_ID:
                        yield variant_id, replic_id, seed

    def get_seeds_list(self):
        return list(self.get_seeds_list_iter())

    def set_seed(self, variant_id: int, replic_id: int, seed: int):
        """
        Set the seed for given variant and replication ID to given seed.
        s from a 2d array (list of list) object. The seeds array is copied entirely, even if it is
        larger than necessary. Array must have at least num_variants x num_replics_per_variant seeds (given at
        construction time).
        :param array2d: the array from which to get the random number generator seeds
        :raises: ValueError, if insufficient seeds in array for number of variants and replications configured
        """
        self._check_data_valid(variant_id, replic_id, seed)
        try:
            self._seeds[variant_id][replic_id] = seed
        except IndexError:
            raise ValueError("IDs must be >= 1, max variant_id is {}, max replic_id is {}"
                             .format(self._num_variants, self._replics_per_variant))

    def get_num_variants(self) -> int:
        """Number of variants supported by this seed table"""
        return self._num_variants

    def get_num_replics_per_variant(self) -> int:
        """Number of replications per variant supported by this seed table"""
        return self._replics_per_variant

    def get_seed(self, variant_id: int, replic_id: int) -> int:
        """
        Get the random seed for given variant and replication IDs. IDs must be in range of num variants and num
        replications per variant.
        """
        return self._seeds[variant_id][replic_id]

    def copy(self, rhs: Decl.SeedTable):
        """
        Copies the seeds from given table into self. Only uses the portion of rhs that fits in self (if rhs larger
        than self), or (if rhs smaller than self) only overwrites portion of self covered by rhs.
        """
        num_variants = min(rhs.num_variants, self._num_variants)
        num_replics_per_variant = min(rhs.num_replics_per_variant, self._replics_per_variant)
        for v_id in range(1, num_variants + 1):
            for r_id in range(1, num_replics_per_variant + 1):
                self._seeds[v_id][r_id] = rhs.get_seed(v_id, r_id)

    def load(self):
        """
        Method used to load a comma delimited CSV file.  Each row of the CSV
        file is a list.  Each list contains a variant, replication and seed information.

        :raises: SeedFileFormatError: Raised when number of rows does not match expected number (where expected
                 number is var*rep.  Can also be raised if seed file contains missing information (ie within a row).
        :raises: SeedFileInvalidInformationError: Raised when invalid data is found within the seed file
                 (ie string values instead of numbers).  Can also be raised if there are duplicates of any
                 variation-replication pair.
        :raises: RuntimeError: if csv path to file not specified
        """
        if self._csv_path is None:
            raise ValueError("Must set seed file path before load()")

        # create temporary empty seeds array with sentinel_value values
        sentinel_value = 0
        new_seeds = [[sentinel_value] * (self._replics_per_variant + MIN_REPLIC_ID)
                     for _ in range(self._num_variants + MIN_VARIANT_ID)]

        log.debug('Loading seeds from {}', self._csv_path)
        with self._csv_path.open('r') as file:
            csv_reader = csv.reader(file, delimiter=",")
            for row_index, row in enumerate(csv_reader):
                line_num = row_index + LINE_OFFSET
                try:
                    variant = int(row[self.VARIANT_COL])
                    replic = int(row[self.REPLIC_COL])
                    seed = int(row[self.SEED_COL])
                except ValueError:
                    if row_index != 0 or tuple(row) != self._csv_header:
                        msg = "Line {}: some values are not numbers".format(line_num)
                        raise SeedFileInvalidInformationError(msg)
                    else:
                        continue  # skip this line

                try:
                    self._check_data_valid(variant, replic, seed)
                except ValueError as exc:
                    raise SeedFileInvalidInformationError("Line #{}: {}".format(line_num, exc))

                # if the var and rep ID are in range, accept; else, ignore it, so bigger tables can be used
                if (variant <= self._num_variants) and (replic <= self._replics_per_variant):
                    value = new_seeds[variant][replic]
                    if value != 0:
                        msg = "Line #{}: seed already defined earlier in file".format(line_num)
                        raise SeedFileInvalidInformationError(msg)
                    new_seeds[variant][replic] = seed

        # check that there are no sentinels left except in first row and col, as this would indicate that
        # there were missing seeds
        for variant_id, var_seeds in enumerate(new_seeds):
            if variant_id >= MIN_VARIANT_ID:
                num_zeros = var_seeds.count(sentinel_value)
                if num_zeros > MIN_REPLIC_ID:
                    raise SeedFileIncompleteError(variant_id, num_zeros)

        self._seeds = new_seeds

    def save_as(self, filepath: Optional[PathType]):
        """
        Saves the seed to file. If the filepath is given, it will be used, and this will become the filepath
        this SeedTable is associated to. Otherwise, the file to save to must have been specified as a setting
        given at initialization of SeedTable(). If not, an exception will be raised. The seed file format is
        same as in load().

        :param filepath: the file to save to (will get overwritten if exists); this replaces the csv_path
            set when the seed table was instantiated; if None, the file path will be based on the
            csv_path that was set when the seed table was instantiated
        """
        if filepath is not None:
            self._csv_path = self.get_csv_file_name(filepath)

        log.info('Saving seeds to {}', self._csv_path)
        with self._csv_path.open('w', newline='') as csv_file:
            csv_writer = csv.writer(csv_file, dialect='excel')
            csv_writer.writerow(self._csv_header)
            for v_id, variant_seeds in enumerate(self._seeds):
                if v_id >= MIN_VARIANT_ID:
                    for r_id, replic_seed in enumerate(variant_seeds):
                        if r_id >= MIN_REPLIC_ID:
                            csv_writer.writerow([v_id, r_id, replic_seed])

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    num_variants = property(get_num_variants)
    num_replics_per_variant = property(get_num_replics_per_variant)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __len__(self):
        """Number of seeds in this table"""
        num_seeds = self._num_variants * self._replics_per_variant
        assert len(self.get_seeds_list()) == num_seeds
        return num_seeds

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _generate_seeds(self):
        """Returns a 2D array of seeds (size (self._num_variants + 1) x (self._replics_per_variant + 1))"""
        log.debug('Generating {}x{} unique seeds', self._num_variants, self._replics_per_variant)
        # get one random seed per replication
        rng = Random()
        seeds = rng.sample(range(MIN_RAND_SEED, MAX_RAND_SEED), self._num_variants * self._replics_per_variant)
        # put in 2D array and return it:
        seeds_array = [[0] * (self._replics_per_variant + MIN_REPLIC_ID)]
        for variant_id in range(1, self._num_variants + 1):
            start_index = (variant_id - 1) * self._replics_per_variant
            stop_index = variant_id * self._replics_per_variant
            variant_seeds = seeds[start_index: stop_index]
            variant_seeds.insert(0, 0)
            seeds_array.append(variant_seeds)
            assert seeds_array[variant_id] is variant_seeds
            assert len(seeds_array[variant_id]) == self._replics_per_variant + 1
        assert len(seeds_array) == self._num_variants + 1

        return seeds_array

    def _check_data_valid(self, variant: int, replic: int, seed: int):
        """
        Determine whether given arguments are valid (in range).
        :param variant:  The variant number to check
        :param replic:  The replication number to check
        :param seed:  The seed to check.
        """
        # TODO build 3: add test for this

        if variant < MIN_VARIANT_ID:
            raise ValueError("variant #{} must be >= 1".format(variant))

        if replic < MIN_REPLIC_ID:
            raise ValueError("replication #{} must be >= 1".format(replic))

        if seed < MIN_RAND_SEED or seed > MAX_RAND_SEED:
            msg = "random seed {} must be in range [{}, {}]".format(seed, MIN_RAND_SEED, MAX_RAND_SEED)
            raise ValueError(msg)
