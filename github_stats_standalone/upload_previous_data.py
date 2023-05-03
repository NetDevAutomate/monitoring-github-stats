#!/usr/bin/env python3

import os
import boto3
import json
import math
from datetime import datetime
from decimal import Decimal

AWS_REGION = "eu-west-1"
DDB_TABLE_NAME = "github_stats"

directory_path = "/Users/taylaand/code/personal/github/monitoring-github-stats/github_stats_standalone/traffic_stats_orig" \
                 "/aws-samples"

# Set up the DynamoDB resource and the table
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
table_name = DDB_TABLE_NAME  # Replace with the actual table name
table = dynamodb_resource.Table(table_name)

def upload_previous_stats(repo_name, views_data, clones_data, table):
    for data_type, data in [("views", views_data), ("clones", clones_data)]:
        if data is None:
            continue

        for item in data:
            item["repo_name"] = repo_name
            item["stat_type"] = data_type
            item["date"] = datetime.strptime(
                item["timestamp"], "%Y-%m-%dT%H:%M:%SZ"
            ).strftime("%Y-%m-%d")

            # Calculate unique value based on 10% of the non-unique count
            uniques_value = math.ceil(item["count"] * 0.1)

            # Update item in the DynamoDB table
            table.update_item(
                Key={
                    "repo_name": item["repo_name"],
                    "stat_type": f"{item['date']}_{item['stat_type']}"
                },
                UpdateExpression="SET #count = :count, #uniques = :uniques",
                ExpressionAttributeNames={
                    "#count": "count",
                    "#uniques": "uniques"
                },
                ExpressionAttributeValues={
                    ":count": Decimal(str(item["count"])),
                    ":uniques": Decimal(str(uniques_value))
                },
                ReturnValues="UPDATED_NEW"
            )

def process_files_in_directory(directory, table):
    files = os.listdir(directory)

    for file in files:
        if not file.endswith(".json"):
            continue

        print(file)

        repo_name, data_type = file.rsplit("_", 1)
        data_type = data_type[:-5]  # Remove '.json' from the data_type

        with open(os.path.join(directory, file), "r") as f:
            data = json.load(f)

        if data_type == "clones":
            clones_data = data["clones"]
            views_data = None
        elif data_type == "views":
            views_data = data["views"]
            clones_data = None

        upload_previous_stats(repo_name, views_data, clones_data, table)

# Replace 'directory_path' with the actual directory containing your JSON files
# process_files_in_directory(directory_path, table)
process_files_in_directory(directory_path, table)
