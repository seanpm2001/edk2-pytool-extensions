# @file report_generator.py
# An executable that allows a user to select a report and execute it on a given database.
##
# Copyright (c) Microsoft Corporation
#
# SPDX-License-Identifier: BSD-2-Clause-Patent
##
"""An executable that allows a user to select a report and execute it on a given database."""
import glob
import logging
import pathlib
import sqlite3
import sys
import tempfile
from argparse import ArgumentParser
from datetime import datetime

from edk2toollib.database import Edk2DB

from edk2toolext import edk2_logging
from edk2toolext.environment.reporttypes import ComponentDumpReport, CoverageReport, UsageReport

REPORTS = [CoverageReport(), ComponentDumpReport(), UsageReport()]


def setup_logging(verbose: bool):
    """Setup logging for the tool."""
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    edk2_logging.setup_section_level()
    edk2_logging.setup_console_logging(logging.DEBUG if verbose else logging.INFO)
    logging.info("Log Started: " + datetime.strftime(datetime.now(), "%A, %B %d, %Y %I:%M%p"))


def parse_args():
    """Parse the arguments for the tool."""
    parser = ArgumentParser("A tool to generate reports on a edk2 workspace.")
    parser.add_argument('--verbose', '--VERBOSE', '-v', dest="verbose", action='store_true', default=False,
                        help='verbose')
    parser.add_argument('-db', '--database', '--DATABASE', dest='database',
                        default=str(pathlib.Path("Report","DATABASE.db")),
                        help="The database to use when generating reports. Can be a comma separated list of db's to "
                             "merge. Globbing is supported.")

    # Register the report arguments as subparser
    subparsers = parser.add_subparsers(dest='cmd', required=[])
    for report in REPORTS:
        name, description = report.report_info()
        report_parser = subparsers.add_parser(name, description=description)
        report.add_cli_options(report_parser)

    return parser.parse_args()

def main():
    """Main functionality of the executable."""
    args = parse_args()
    setup_logging(args.verbose)

    # Verify arguments
    to_merge = []
    database_list = args.database.split(",")
    for database in database_list:
        found = list(glob.glob(database))
        if not found:
            logging.warning(f"No database at path: [{database}]")
        else:
            to_merge.extend(list(glob.glob(database)))

    if not to_merge:
        logging.error("No databases found.")
        return -1

    for database in to_merge:
        if not pathlib.Path(database).exists():
            logging.error(f"Database does not exist: [{database}]")
            return -1

    if len(to_merge) == 1:
        logging.info(f"Single Database file found at: {to_merge[0]}")
        db_path = to_merge[0]
    else:
        logging.info("Multiple Database files found...")
        db_path = merge_databases(to_merge).name

    del args.database
    cmd = args.cmd
    del args.cmd

    with Edk2DB(db_path = db_path) as db:
        for report in REPORTS:
            name, _ = report.report_info()
            if name == cmd:
                return report.run_report(db, args)
    return -1

def merge_databases(databases: list[str]) -> str:
    """Performs an in-memory merge of databases and provides a string path to the temporary file."""
    logging.info(f"Merging database: {databases[0]}")
    db = pathlib.Path(databases[0])
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db.write(db.read_bytes())

    conn = sqlite3.connect(temp_db.name)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for database in databases[1:]:
        logging.info(f"Merging database: {database}")
        conn.execute(f"ATTACH DATABASE '{database}' AS temp_db")
        for table, in tables:
            conn.execute(f"INSERT OR REPLACE INTO main.{table} SELECT * FROM temp_db.{table};")
        conn.commit()
        conn.execute("DETACH DATABASE temp_db;")
        conn.commit()

    return temp_db


def go():
    """Main entry into the report generator tool.

    Sets up the logger for the tool and then runs the tool.
    """
    # setup main console as logger
    logger = logging.getLogger('')
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)s - %(message)s")
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # call main worker function
    retcode = main()

    if retcode != 0:
        logging.critical("Failed.  Return Code: %d" % retcode)
    else:
        logging.critical("Success!")
    # end logging
    logging.shutdown()
    sys.exit(retcode)


if __name__ == '__main__':
    go()
