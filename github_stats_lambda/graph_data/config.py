import os
import sys
from datetime import datetime

PROGRAM_NAME = os.path.basename(sys.argv[0])
APP_NAME = os.path.basename(sys.argv[0])
FILEPATH = os.getcwd()
DATA_DIR = "data"
NOW = datetime.now().strftime("%d-%m-%Y-%H-%M")
AWS_REGION = "eu-west-1"
DDB_TABLE_NAME = "github_stats"
OUTPUT_FILE = f"{FILEPATH}/{DATA_DIR}/github_stats-{NOW}.pdf"
REGION = "eu-west-1"
LAMBDA_FUNCTION_NAME = "GithubStatsFunction"
