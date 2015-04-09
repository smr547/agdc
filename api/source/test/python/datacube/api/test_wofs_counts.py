import os
import unittest
from datacube.api.model import DatasetType, Tile, Cell, Satellite
from datacube.config import Config, DbCredentials
from datetime import datetime
from datacube.api.query import list_tiles_as_list, TimeInterval, DatacubeQueryContext
import logging

logging.basicConfig(level=logging.INFO)

class TestQueryWrapper(unittest.TestCase):

    def test_get_all_cell_tiles_with_cube_context(self):
        cube = DatacubeQueryContext()
        filename = cube.tile_list_to_file( \
            range(111, 154), \
            range(-46, -3), 
            [Satellite.LS5, Satellite.LS7], \
            TimeInterval(datetime(1950,1,1), datetime(2050,1,1)), \
            [DatasetType.ARG25, DatasetType.PQ25])
        print filename


if __name__ == '__main__':
    unittest.main()
