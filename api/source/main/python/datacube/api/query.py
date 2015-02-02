#!/usr/bin/env python

# ===============================================================================
# Copyright (c)  2014 Geoscience Australia
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither Geoscience Australia nor the names of its contributors may be
#       used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ===============================================================================


__author__ = "Simon Oldfield"


from enum import Enum
import logging
import psycopg2
import psycopg2.extras
import sys
from model import Tile, Cell
from datetime import datetime

_log = logging.getLogger(__name__)


class TileClass(Enum):
    __order__ = "SINGLE MOSAIC"

    SINGLE = 1
    MOSAIC = 4


TILE_CLASSES = [TileClass.SINGLE, TileClass.MOSAIC]


class TileType(Enum):
    __order__ = "ONE_DEGREE"

    ONE_DEGREE = 1


TILE_TYPE = TileType.ONE_DEGREE


class ProcessingLevel(Enum):
    __order__ = "ORTHO NBAR PQA FC L1T MAP DSM DEM DEM_S DEM_H"

    ORTHO = 1
    NBAR = 2
    PQA = 3
    FC = 4
    L1T = 5
    MAP = 10
    DSM = 100
    DEM = 110
    DEM_S = 120
    DEM_H = 130


class SortType(Enum):
    __order__ = "ASC DESC"

    ASC = "asc"
    DESC = "desc"


def print_tile(tile):
    _log.debug("id=%7d x=%3d y=%3d start=[%s] end=[%s] year=[%4d] month=[%2d] datasets=[%s]",
               tile.acquisition_id, tile.x, tile.y,
               tile.start_datetime, tile.end_datetime,
               tile.end_datetime_year, tile.end_datetime_month,
               ",".join("|".join([ds.type_id, ds.path]) for ds in tile.datasets))


#
# TODO refactor common code (and SQL) from these methods
# TODO properly implement them
# TODO take some notice of requested dataset types
# TODO support DSM tiles in standard list methods
#

###
# CELLS...
###

# Cells that we DO have

def list_cells(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    Deprecated: Move to using explicit as_list or as_generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Cell]
    """
    return list_cells_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort)


def list_cells_as_list(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria AS A REUSABLE LIST rather than as a one-use-generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Cell]
    """
    return list(list_cells_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort))


# For this the datasets are the REQUIRED ones (since we aren't returning datasets here)

def list_cells_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Cell]
    """
    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        sql = """
            select distinct nbar.x_index, nbar.y_index
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = %(level_nbar)s
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = %(level_pqa)s
                ) as pq on
                    pq.acquisition_id=acquisition.acquisition_id
                    and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
                    and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = %(level_fc)s
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [TILE_TYPE.value],
                  "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "acq_min": acq_min, "acq_max": acq_max,
                  "level_nbar": ProcessingLevel.NBAR.value,
                  "level_pqa": ProcessingLevel.PQA.value,
                  "level_fc": ProcessingLevel.FC.value}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in result_generator(cursor):
            _log.debug(record)
            yield Cell.from_db_record(record)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_cells_to_file(x, y, satellites, years, datasets, filename, database, user, password, host=None, port=None, sort=SortType.ASC):

    conn = cursor = None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor()
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        sql = """
            copy (
            select distinct nbar.x_index, nbar.y_index
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 3
                ) as pq on
                    pq.acquisition_id=acquisition.acquisition_id
                    and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
                    and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and extract(year from end_datetime) = ANY(%(year)s)

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ) to STDOUT csv header delimiter ',' escape '"' null '' quote '"'
            ;
        """.format(sort=sort.value)

        # TODO - think about the sort here for the y value?

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "year": years}

        if filename:
            with open(filename, "w") as f:
                cursor.copy_expert(cursor.mogrify(sql, params), f)
        else:
            cursor.copy_expert(cursor.mogrify(sql, params), sys.stdout)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()

    finally:

        conn = cursor = None


# Cells that we DON'T have

# TODO currently hard coded to fractional cover

def list_cells_missing(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    Deprecated: Move to using explicit as_list or as_generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Cell]
    """
    return list_cells_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort)


def list_cells_missing_as_list(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria AS A REUSABLE LIST rather than as a one-use-generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Cell]
    """
    return list(list_cells_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort))


def list_cells_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        sql = """
            select distinct nbar.x_index, nbar.y_index
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            left outer join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s
                and fc.acquisition_id is null

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "acq_min": acq_min, "acq_max": acq_max}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in result_generator(cursor):
            _log.debug(record)
            yield Cell.from_db_record(record)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_cells_missing_to_file(x, y, satellites, years, datasets, filename, database, user, password, host=None, port=None, sort=SortType.ASC):

    conn = cursor = None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor()
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        sql = """
            copy (
            select distinct nbar.x_index, nbar.y_index
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            left outer join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s
                and fc.acquisition_id is null

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ) to STDOUT csv header delimiter ',' escape '"' null '' quote '"'
            ;
        """.format(sort=sort.value)

        # TODO - think about the sort here for the y value?

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "year": years}

        if filename:
            with open(filename, "w") as f:
                cursor.copy_expert(cursor.mogrify(sql, params), f)
        else:
            cursor.copy_expert(cursor.mogrify(sql, params), sys.stdout)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()

    finally:

        conn = cursor = None


###
# TILES...
###

# Tiles that we DO have

def list_tiles(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    Deprecated: Move to using explicit as_list or as_generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list_tiles_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort)


def list_tiles_as_list(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria AS A REUSABLE LIST rather than as a one-use-generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list(list_tiles_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort))


def list_tiles_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        sql = """
            select
                acquisition.acquisition_id, satellite_tag as satellite, start_datetime, end_datetime,
                extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
                NBAR.x_index, NBAR.y_index, point(NBAR.x_index, NBAR.y_index) as xy,
                ARRAY[
                    ['ARG25', NBAR.tile_pathname],
                    ['PQ25', PQA.tile_pathname],
                    ['FC25', FC.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as NBAR on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 3
                ) as PQA on
                    PQA.acquisition_id=acquisition.acquisition_id
                    and PQA.x_index=NBAR.x_index and PQA.y_index=NBAR.y_index
                    and PQA.tile_type_id=NBAR.tile_type_id and PQA.tile_class_id=NBAR.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as FC on
                    FC.acquisition_id=acquisition.acquisition_id
                    and FC.x_index=NBAR.x_index and FC.y_index=NBAR.y_index
                    and FC.tile_type_id=NBAR.tile_type_id and FC.tile_class_id=NBAR.tile_class_id
            where
                NBAR.tile_type_id = ANY(%(tile_type)s) and NBAR.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and NBAR.x_index = ANY(%(x)s) and NBAR.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s

            order by end_datetime {sort}, satellite asc
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "acq_min": acq_min, "acq_max": acq_max}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in result_generator(cursor):
            _log.debug(record)
            yield Tile.from_db_record(record)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_tiles_to_file(x, y, satellites, years, datasets, filename, database, user, password, host=None, port=None, sort=SortType.ASC):

    conn = cursor = None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor()
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        sql = """
            copy (
            select
                acquisition.acquisition_id, satellite_tag as satellite, start_datetime, end_datetime,
                extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
                nbar.x_index, nbar.y_index, point(nbar.x_index, nbar.y_index) as xy,
                ARRAY[
                    ['ARG25', nbar.tile_pathname],
                    ['PQ25', pq.tile_pathname],
                    ['FC25', fc.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 3
                ) as pq on
                    pq.acquisition_id=acquisition.acquisition_id
                    and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
                    and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and extract(year from end_datetime) = ANY(%(year)s)

            order by end_datetime {sort}, satellite asc
            ) to STDOUT csv header delimiter ',' escape '"' null '' quote '"'
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "year": years}

        if filename:
            with open(filename, "w") as f:
                cursor.copy_expert(cursor.mogrify(sql, params), f)
        else:
            cursor.copy_expert(cursor.mogrify(sql, params), sys.stdout)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()

    finally:

        conn = cursor = None


# Tiles that we DON'T have

def list_tiles_missing(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    Deprecated: Move to using explicit as_list or as_generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list_tiles_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort)


def list_tiles_missing_as_list(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria AS A REUSABLE LIST rather than as a one-use-generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list(list_tiles_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host, port, sort))


def list_tiles_missing_as_generator(x, y, satellites, acq_min, acq_max, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    :type x: list[int]
    :type y: list[int]
    :type satellites: list[datacube.api.model.Satellite]
    :type acq_min: datetime.date
    :type acq_max: datetime.date
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        sql = """
            select
                acquisition.acquisition_id, satellite_tag as satellite, start_datetime, end_datetime,
                extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
                NBAR.x_index, NBAR.y_index, point(NBAR.x_index, NBAR.y_index) as xy,
                ARRAY[
                    ['ARG25', NBAR.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            left outer join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s
                and fc.acquisition_id is null

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "acq_min": acq_min, "acq_max": acq_max}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in result_generator(cursor):
            _log.debug(record)
            yield Tile.from_db_record(record)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_tiles_missing_to_file(x, y, satellites, years, datasets, filename, database, user, password, host=None, port=None, sort=SortType.ASC):

    conn = cursor = None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor()
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        sql = """
            copy (
            select
                acquisition.acquisition_id, satellite_tag as satellite, start_datetime, end_datetime,
                extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
                NBAR.x_index, NBAR.y_index, point(NBAR.x_index, NBAR.y_index) as xy,
                ARRAY[
                    ['ARG25', NBAR.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            left outer join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and end_datetime::date between %(acq_min)s and %(acq_max)s
                and fc.acquisition_id is null

            order by nbar.x_index {sort}, nbar.y_index {sort}
            ) to STDOUT csv header delimiter ',' escape '"' null '' quote '"'
            ;
        """.format(sort=sort.value)

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": x, "y": y,
                  "year": years}

        if filename:
            with open(filename, "w") as f:
                cursor.copy_expert(cursor.mogrify(sql, params), f)
        else:
            cursor.copy_expert(cursor.mogrify(sql, params), sys.stdout)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()

    finally:

        conn = cursor = None


# DEM/DSM tiles - quickie to get DEM/DSM tiles for WOFS - note they have no acquisition information!!!!

def list_tiles_dtm(x, y, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    Deprecated: Move to using explicit as_list or as_generator

    :type x: list[int]
    :type y: list[int]
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list_tiles_dtm_as_generator(x, y, datasets, database, user, password, host, port, sort)


def list_tiles_dtm_as_list(x, y, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria AS A REUSABLE LIST rather than as a one-use-generator

    :type x: list[int]
    :type y: list[int]
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """
    return list(list_tiles(x, y, datasets, database, user, password, host, port, sort))


def list_tiles_dtm_as_generator(x, y, datasets, database, user, password, host=None, port=None, sort=SortType.ASC):

    """
    Return a list of cells matching the criteria as a SINGLE-USE generator

    :type x: list[int]
    :type y: list[int]
    :type datasets: list[datacube.api.model.DatasetType]
    :type database: str
    :type user: str
    :type password: str
    :type host: str
    :type port: int
    :type sort: SortType
    :rtype: list[datacube.api.model.Tile]
    """

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       x/y range
        #
        #   request which datasets they want
        #       DSM
        #       DEM
        #       DEM SMOOTHED
        #       DEM HYDROLOGICALLY ENFORCED

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        # select
        #   dem.acquisition_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
        # from tile
        # join dataset dem on dem.dataset_id=tile.dataset_id and dem.level_id=100
        # where tile.tile_type_id = 1 and tile.tile_class_id in (1,4) and tile.x_index in (120) and tile.y_index in (-20) ;

        sql = """
            select
                null acquisition_id, null satellite, null start_datetime, null end_datetime,
                null end_datetime_year, null end_datetime_month,
                dsm.x_index, dsm.y_index, point(dsm.x_index, dsm.y_index) as xy,
                ARRAY[
                    ['DSM', DSM.tile_pathname],
                    ['DEM', DEM.tile_pathname],
                    ['DEM_HYDROLOGICALLY_ENFORCED', DEM_H.tile_pathname],
                    ['DEM_SMOOTHED', DEM_S.tile_pathname]
                    ] as datasets
            from
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 100
                ) as DSM
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 110
                ) as DEM on
                        DEM.x_index=DSM.x_index and DEM.y_index=DSM.y_index
                    and DEM.tile_type_id=DSM.tile_type_id and DEM.tile_class_id=DSM.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 120
                ) as DEM_S on
                        DEM_S.x_index=DSM.x_index and DEM_S.y_index=DSM.y_index
                    and DEM_S.tile_type_id=DSM.tile_type_id and DEM_S.tile_class_id=DSM.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 130
                ) as DEM_H on
                        DEM_H.x_index=DSM.x_index and DEM_H.y_index=DSM.y_index
                    and DEM_H.tile_type_id=DSM.tile_type_id and DEM_H.tile_class_id=DSM.tile_class_id
            where
                DSM.tile_type_id = ANY(%(tile_type)s) and DSM.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and DSM.x_index = ANY(%(x)s) and DSM.y_index = ANY(%(y)s)
            ;
        """.format()

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "x": x, "y": y}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in result_generator(cursor):
            _log.debug(record)
            yield Tile.from_db_record(record)

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


###
# Other stuff - mostly incomplete...
###

def visit_tiles(x, y, satellites, years, datasets, database, user, password, host=None, port=None, func=print_tile):

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        # So in terms of SQL first filter back to that tile list

        # select acquisition.acquisition_id, satellite_tag, start_datetime, end_datetime,
        # extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
        # nbar.tile_pathname, pq.tile_pathname, fc.tile_pathname
        # from acquisition
        # join satellite on satellite.satellite_id=acquisition.satellite_id
        # join
        # 	(
        # 	select
        # 		dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
        # 	from tile
        # 	join dataset on dataset.dataset_id=tile.dataset_id
        # 	where dataset.level_id = 2
        # 	) as nbar on nbar.acquisition_id=acquisition.acquisition_id
        # join
        # (
        # select
        # 	dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
        # from tile
        # join dataset on dataset.dataset_id=tile.dataset_id
        # where dataset.level_id = 3
        # ) as pq on
        # 	pq.acquisition_id=acquisition.acquisition_id
        # 	and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
        # 	and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
        # join
        # (
        # select
        # 	dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
        # from tile
        # join dataset on dataset.dataset_id=tile.dataset_id
        # where dataset.level_id = 4
        # ) as fc on
        # 	fc.acquisition_id=acquisition.acquisition_id
        # 	and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
        # 	and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
        # where
        # nbar.tile_type_id in (1) and nbar.tile_class_id in (1,3) -- mandatory
        # and satellite.satellite_id in (1,2,3)
        # and nbar.x_index in (148,149) and nbar.y_index in (-35, -36)
        # and date_trunc('year', end_datetime) = '2012-01-01'::timestamp
        # ;

        sql = """
            select
                acquisition.acquisition_id, satellite_tag, start_datetime, end_datetime,
                extract(year from end_datetime) as end_datetime_year, extract(month from end_datetime) as end_datetime_month,
                nbar.x_index, nbar.y_index, point(nbar.x_index, nbar.y_index) as xy,
                ARRAY[
                    ['ARG25', nbar.tile_pathname],
                    ['PQ25', pq.tile_pathname],
                    ['FC25', fc.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 3
                ) as pq on
                    pq.acquisition_id=acquisition.acquisition_id
                    and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
                    and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_id = ANY(%(satellite)s)
                and nbar.x_index = ANY(%(x)s) and nbar.y_index = ANY(%(y)s)
                and extract(year from end_datetime) = ANY(%(year)s)
            ;
        """

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "x": [x], "y": [y],
                  "year": years}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        for record in cursor:
            _log.debug(record)
            func(Tile.from_db_record(record))

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_tiles_wkt(wkt, satellites, years, datasets, database, user, password, host=None, port=None):

    conn, cursor = None, None

    try:
        # connect to database

        connection_string = ""

        if host:
            connection_string += "host={host}".format(host=host)

        if port:
            connection_string += " port={port}".format(port=port)

        connection_string += " dbname={database} user={user} password={password}".format(database=database, user=user, password=password)

        conn = psycopg2.connect(connection_string)

        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("set search_path to {schema}, public".format(schema="gis, topology, ztmp"))

        # Should the DB model be changed so that DATASET FKs to TILE not TILE FKs to DATASET?

        # This query allows the user to specify
        #   filter results by
        #       satellite
        #       x/y range
        #       time range (use end_datetime)?
        #
        #   request which datasets they want
        #       NBAR
        #       PQ
        #       FC

        # It also needs to internally filter to
        #   tile.tile_type_id in (1)
        #   tile.tile_class_id in (1,3)

        sql = """
            select
                acquisition.acquisition_id, satellite_tag as satellite, start_datetime, end_datetime,
                extract(year from end_datetime)::integer as end_datetime_year, extract(month from end_datetime)::integer as end_datetime_month,
                nbar.x_index, nbar.y_index, point(nbar.x_index, nbar.y_index) as xy,
                ARRAY[
                    ['ARG25', nbar.tile_pathname],
                    ['PQ25', pq.tile_pathname],
                    ['FC25', fc.tile_pathname]
                    ] as datasets
            from acquisition
            join satellite on satellite.satellite_id=acquisition.satellite_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 2
                ) as nbar on nbar.acquisition_id=acquisition.acquisition_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 3
                ) as pq on
                    pq.acquisition_id=acquisition.acquisition_id
                    and pq.x_index=nbar.x_index and pq.y_index=nbar.y_index
                    and pq.tile_type_id=nbar.tile_type_id and pq.tile_class_id=nbar.tile_class_id
            join
                (
                select
                    dataset.acquisition_id, tile.dataset_id, tile.x_index, tile.y_index, tile.tile_pathname, tile.tile_type_id, tile.tile_class_id
                from tile
                join dataset on dataset.dataset_id=tile.dataset_id
                where dataset.level_id = 4
                ) as fc on
                    fc.acquisition_id=acquisition.acquisition_id
                    and fc.x_index=nbar.x_index and fc.y_index=nbar.y_index
                    and fc.tile_type_id=nbar.tile_type_id and fc.tile_class_id=nbar.tile_class_id
            join tile_footprint on
                tile_footprint.x_index = nbar.x_index
                and tile_footprint.y_index = nbar.y_index
                and tile_footprint.tile_type_id = nbar.tile_type_id

            where
                nbar.tile_type_id = ANY(%(tile_type)s) and nbar.tile_class_id = ANY(%(tile_class)s) -- mandatory
                and satellite.satellite_tag = ANY(%(satellite)s)
                and st_intersects(tile_footprint.bbox, st_geomfromtext(%(polygon)s, 4326))
                and extract(year from end_datetime) = ANY(%(year)s)

            order by end_datetime asc, satellite asc
            ;
        """

        params = {"tile_type": [1], "tile_class": [tile_class.value for tile_class in TILE_CLASSES],
                  "satellite": [satellite.value for satellite in satellites],
                  "polygon": wkt,
                  "year": years}

        _log.debug(cursor.mogrify(sql, params))

        cursor.execute(sql, params)

        tiles = []

        for record in cursor:
            _log.debug(record)
            tiles.append(Tile.from_db_record(record))

        return tiles

    except Exception as e:

        _log.error("Caught exception %s", e)
        conn.rollback()


def list_tiles_wkt_to_file(wkt, years, datasets, format, filename, database, user, password, host=None, port=None):
    pass


def visit_tiles_wkt(wkt, years, datasets, database, user, password, host=None, port=None):
    pass


def result_generator(cursor, size=100):

    while True:

        results = cursor.fetchmany(size)

        if not results:
            break

        for result in results:
            yield result

class TimeInterval(object):
    """
    A TimeInterval represents an interval of time from a start instant up to (but not including)
    an end instant. Instants are represented by datetime objects. Inspired by the Java JODA package.
    """
   
    # define constants for the beginning and end of time
    # NOTE: we could get rid of these but the SQL gets a bit messy

    MIN_INSTANT = datetime(1900, 1, 1)
    MAX_INSTANT = datetime(3999, 1, 1)
       

    def __init__(self, start_datetime=MIN_INSTANT, end_datetime=MAX_INSTANT):
        """
        Construct a TimeInterval object from the supplied start and end datetime instances.
        Closed and open ended intervals (forwards and backwards) are supported, as is the "unspecified 
        interval" consisting of all time (the "give me everything you've got" interval).

        e.g:
            TimeInterval(datetime(2013,1,1), datetime(2015,12,31))  # three years from 1/1/13
            TimeInterval(datetime(2013,1,1))   # all time beginning from 1/1/13
            TimeInterval(end_datetime=datetime(2013,1,1)) # all time up to the end of 2012
            TimeInterval() # all time (forever), aka: TimeInterval not specified
        """
        assert(isinstance(start_datetime, datetime))
        assert(isinstance(end_datetime, datetime))
        assert(end_datetime > start_datetime)

        self.start = start_datetime
        self.end = end_datetime

class DatacubeQueryContext(object):
    """
    An instance of DatacubeQueryContext provides the ablility to query a selected Datacube
    """

    def __init__(self, db_credentials):
        """
        Instantiate a new DatacubeQueryContext using the supplied DbCredentials object
        """
        self.db_credentials = db_credentials

    def tile_list(self, x_list, y_list, satellite_list, time_interval, dataset_list, sort=SortType.ASC):
        print str(self.db_credentials)
        return list_tiles_as_list( \
            x_list, \
            y_list, \
            satellite_list, \
            time_interval.start, \
            time_interval.end, \
            dataset_list, \
            database=self.db_credentials.database, \
            user=self.db_credentials.user, \
            password=self.db_credentials.password, \
            host=self.db_credentials.host, \
            port=self.db_credentials.port, \
            sort=sort)
