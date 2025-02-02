"""
Consolidate data into the database.
"""

import logging
import os
from typing import Dict
from zipfile import ZipFile

import duckdb
import requests

from ._common import CACHE_FOLDER, DUCKDB_FILE, clear_cache

logger = logging.getLogger(__name__)

def get_yearly_dataset_infos(year:str) -> Dict[str,str]:
    """
    Returns information for yearly dataset extract of the SISE Eaux datasets.
    The data comes from https://www.data.gouv.fr/fr/datasets/resultats-du-controle-sanitaire-de-leau-distribuee-commune-par-commune/
    For each year a dataset is downloadable on a URL like this (ex. 2024):
        https://www.data.gouv.fr/fr/datasets/r/84a67a3b-08a7-4001-98e6-231c74a98139
    The id of the dataset is the last part of this URL
    The name of the dataset is dis-YEAR.zip (but the format could potentially change).
    :param year: The year from which we want to get the dataset information.
    :return: A dict with the id and name of the dataset.
    """
    dis_files_info_by_year = {
        "2024": {"id": "84a67a3b-08a7-4001-98e6-231c74a98139", "name" : "dis-2024.zip"},
        "2023": {"id":"c89dec4a-d985-447c-a102-75ba814c398e", "name" : "dis-2023.zip"},
        "2022": {"id":"a97b6074-c4dd-4ef2-8922-b0cf04dbff9a", "name" : "dis-2022.zip"},
        "2021": {"id":"d2b432cc-3761-44d3-8e66-48bc15300bb5", "name" : "dis-2021.zip"},
        "2020": {"id":"a6cb4fea-ef8c-47a5-acb3-14e49ccad801", "name" : "dis-2020.zip"},
        "2019": {"id":"861f2a7d-024c-4bf0-968b-9e3069d9de07", "name" : "dis-2019.zip"},
        "2018": {"id":"0513b3c0-dc18-468d-a969-b3508f079792", "name" : "dis-2018.zip"},
        "2017": {"id":"5785427b-3167-49fa-a581-aef835f0fb04", "name" : "dis-2017.zip"},
        "2016": {"id":"483c84dd-7912-483b-b96f-4fa5e1d8651f", "name" : "dis-2016.zip"}
    }
    return dis_files_info_by_year[year]


def process_sise_eaux_dataset_2024(year: str):
    """
    Downloads from www.data.gouv.fr the SISE-Eaux dataset for one year
    :param year: The year from which we want to download the dataset
    :return: Create or replace the associated tables in the duckcb database.
        It adds the column "annee_prelevement" based on year as an integer.
    """

    yearly_dataset_info = get_yearly_dataset_infos(year=year)

    # Dataset specific constants
    DATA_URL = f"https://www.data.gouv.fr/fr/datasets/r/{yearly_dataset_info['id']}"
    ZIP_FILE = os.path.join(CACHE_FOLDER, yearly_dataset_info["name"])
    EXTRACT_FOLDER = os.path.join(CACHE_FOLDER, f"raw_data_{year}")

    FILES = {
        "communes": {
            "filename_prefix": f"DIS_COM_UDI_",
            "file_extension": ".txt",
            "table_name": f"sise_communes",
        },
        "prelevements": {
            "filename_prefix": f"DIS_PLV_",
            "file_extension": ".txt",
            "table_name": f"sise_prelevements",
        },
        "resultats": {
            "filename_prefix": f"DIS_RESULT_",
            "file_extension": ".txt",
            "table_name": f"sise_resultats",
        },
    }

    logger.info(f"Downloading and extracting SISE-Eaux dataset for {year}...")
    response = requests.get(DATA_URL, stream=True)
    with open(ZIP_FILE, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info("Extracting files...")
    with ZipFile(ZIP_FILE, "r") as zip_ref:
        zip_ref.extractall(EXTRACT_FOLDER)

    logger.info("Creating tables in the database...")
    conn = duckdb.connect(DUCKDB_FILE)

    for file_info in FILES.values():
        filepath = os.path.join(
            EXTRACT_FOLDER,
            f"{file_info['filename_prefix']}{year}{file_info['file_extension']}",
        )

        if check_table_existence(conn=conn, table_name=f"{file_info['table_name']}"):
            query = f"""
                DELETE FROM {f"{file_info['table_name']}"}
                WHERE annee_prelevement = {year}
                ;
            """
            conn.execute(query)
            query_start = f"INSERT INTO {f'{file_info["table_name"]}'} "

        else:
            query_start = f"CREATE TABLE {f'{file_info["table_name"]}'} AS "

        query_select = f"""
            SELECT 
                *,
                CAST({year} as INTEGER) AS annee_prelevement
            FROM read_csv('{filepath}', header=true, delim=',');
        """

        conn.execute(query_start + query_select)

    conn.close()

    logger.info("Cleaning up...")
    clear_cache()

    return True


def check_table_existence(conn, table_name):
    query = f"""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = '{table_name}'
        """
    conn.execute(query)
    return list(conn.fetchone())[0] == 1


def execute():
    process_sise_eaux_dataset_2024(year="2024")
