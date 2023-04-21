import json
import logging
import os
from datetime import datetime

import requests
from boto3 import resource
from botocore.exceptions import ClientError
from github import Github

logging.basicConfig()
logger = logging.getLogger("GitHubStats")
logger.setLevel(logging.INFO)


def create_table_if_not_exists(dynamodb_resource, table_name):
    try:
        table = dynamodb_resource.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "repo_name", "KeyType": "HASH"},
                {"AttributeName": "stat_type", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "repo_name", "AttributeType": "S"},
                {"AttributeName": "stat_type", "AttributeType": "S"},
            ],
            ProvisionedThroughput={
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5,
            },
        )
        table.wait_until_exists()
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceInUseException":
            raise
        table = dynamodb_resource.Table(table_name)
    return table

def lambda_handler(event, context):
    date_today = datetime.today().strftime("%Y-%m-%d")

    table_name = os.environ["TABLE_NAME"]
    access_token = os.environ["GITHUB_TOKEN"]
    team_name = os.environ["TEAM_NAME"]
    org_name = os.environ["ORG_NAME"]

    # Get DynamoDB table resource
    dynamodb_resource = resource("dynamodb", region_name="eu-west-1")

    try:
        table = dynamodb_resource.Table(table_name)
        table.load()
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            table = create_table_if_not_exists(dynamodb_resource, table_name)
        else:
            raise

    # Get all repos in a team
    repos = get_all_repos(access_token, team_name, org_name)

    for repo in repos:
        logger.info(f"Fetching data for {repo}...")

        views_data = fetch_traffic_stats(repo, "views", access_token)
        clones_data = fetch_traffic_stats(repo, "clones", access_token)

        # Write stats to DynamoDB
        for data in [views_data, clones_data]:
            if data:
                for item in data:
                    item["repo_name"] = repo
                    item["stat_type"] = item["type"]
                    item["date"] = datetime.strptime(
                        item["timestamp"], "%Y-%m-%dT%H:%M:%SZ"
                    ).strftime("%Y-%m-%d")

                    # Update item in the DynamoDB table
                    table.put_item(
                        Item={
                            "repo_name": item["repo_name"],
                            "stat_type": item["stat_type"],
                            "count": item["count"],
                            "uniques": item["uniques"],
                            "date": item["date"]
                        }
                    )

    return {
        "statusCode": 200,
        "body": json.dumps("Stats updated successfully."),
    }



# Function to get all repos in a team
def get_all_repos(access_token, team_name, org_name):
    repo_list = []

    g = Github(access_token)
    org = g.get_organization(org_name)
    team = org.get_team_by_slug(team_name)
    repos = team.get_repos()

    for repo in repos:
        if repo.archived or repo.private:
            continue
        repo_list.append(repo.full_name)

    return repo_list


# Function to fetch traffic stats from GitHub API
def fetch_traffic_stats(repo, stat_type, access_token):
    url = f"https://api.github.com/repos/{repo}/traffic/{stat_type}"
    headers = {"Authorization": f"token {access_token}"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        for item in data[stat_type]:
            item["type"] = stat_type

        return data[stat_type]
    except requests.exceptions.RequestException as e:
        logger.info(f"Error fetching {stat_type} data for {repo}: {e}")
        return None
