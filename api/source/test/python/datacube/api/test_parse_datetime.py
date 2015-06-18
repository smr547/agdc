import os
import unittest
from datacube.api.model import parse_datetime
from datetime import datetime


class TestConfig(unittest.TestCase):

    def setUp(self):
        self.with_micros = datetime(2014, 10, 25, 11, 3, 21, 123456)
        self.no_micros = datetime(2014, 10, 25, 11, 3, 21)

    def tearDown(self):
        pass

    def test_with_micros(self):
        dt_string = "2014-10-25 11:03:21.123456"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.with_micros)

    def test_with_micros_dash_time_sep(self):
        dt_string = "2014-10-25 11-03-21.123456"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.with_micros)

    def test_with_micros_T_separator(self):
        dt_string = "2014-10-25T11:03:21.123456"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.with_micros)

    def test_with_no_micros(self):
        dt_string = "2014-10-25 11:03:21"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.no_micros)
        self.assertEqual(self.no_micros.microsecond, 0)

    def test_with_zero_micros(self):
        dt_string = "2014-10-25 11:03:21.0"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.no_micros)
        self.assertEqual(self.no_micros.microsecond, 0)

    def test_find_timestamp_in_filepath(self):
        dt_string = "/g/data/rs0/tiles/EPSG4326_1deg_0.00025pixel/LS5_TM/150_-034/2007/mosaic_cache/LS5_TM_NBAR_150_-034_2014-10-25T11-03-21.123456.vrt"
        dt = parse_datetime(dt_string)
        self.assertTrue(dt is not None)
        self.assertEqual(dt, self.with_micros)

if __name__ == '__main__':
    unittest.main()
