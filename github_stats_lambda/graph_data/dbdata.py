#!/usr/bin/env python3
import argparse
import json
import os
import sys
import threading
import typing
import webbrowser
from queue import Queue
from time import sleep, time

import boto3
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table

import config

console = Console()

# Create command-line argument parser and define arguments
parser = argparse.ArgumentParser(
    description=f"{config.APP_NAME}",
)

group = parser.add_mutually_exclusive_group(required=False)
group.add_argument("--run", "-r", action="store_true", help="Visualise data with current statistics")
parser.add_argument("--update", "-u", action="store_true", help="Invoke the Lambda function to update the statistics")
group.add_argument("--list", "-l", action="store_true", help="List Repositories")

args = parser.parse_args()


def invoke_lambda_function(*, function_name: str = None, payload: typing.Mapping[str, str] = None,
                           response_queue: Queue = None):
    if function_name is None:
        raise Exception('ERROR: functionName parameter cannot be NULL')

    payload_str = json.dumps(payload)
    payload_bytes_arr = bytes(payload_str, encoding='utf8')

    client = boto3.client('lambda', region_name=config.AWS_REGION)
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=payload_bytes_arr
    )

    response_payload = response['Payload'].read().decode('utf-8')
    response_queue.put(response_payload)


def update_stats(invoke_lambda):
    payload_obj = {"Key": "Value"}  # Dummy test payload to invoke the Lambda function

    # Create a queue to hold the response from the invokeLambdaFunction
    response_queue = Queue()

    # Create a thread to invoke the lambda function
    thread = threading.Thread(target=invoke_lambda_function,
                              kwargs={"function_name": invoke_lambda, "payload": payload_obj,
                                      "response_queue": response_queue})
    thread.start()

    # Use rich to display a progress bar while the Lambda function is invoked asynchronously
    progress = Progress(
        TextColumn("[bold blue]{task.fields[status]}[/bold blue]", justify="right"),
        BarColumn(bar_width=None),
        "[bold blue]{task.fields[message]}[/bold blue]",
        console=console,
        auto_refresh=True,
    )

    task = progress.add_task("[green]Updating...[/green]", status="working", message="Starting")

    progress.start()

    start_time = time()
    while thread.is_alive():
        elapsed_time = time() - start_time
        progress.update(task, advance=elapsed_time / 10, status="working", message="Updating...")
        sleep(0.4)

    progress.update(task, advance=100, status="done", message="Finished")

    progress.stop()

    # Wait for the thread to finish and print the response
    thread.join()
    response_payload = response_queue.get()
    response_dict = json.loads(response_payload)
    print(response_dict)
    if response_dict["statusCode"] == 200 and response_dict["body"] == "\"Stats updated successfully.\"":
        console.print("[green]Success[/green], stats updated")
    else:
        console.print("[red]Issue[/red], stats not updated")
        sys.exit(1)


def visualize_data(ddb_table_name):
    # create the data directory if it does not exist
    os.makedirs(config.DATA_DIR, exist_ok=True)

    # initialize the dynamodb resource
    dynamodb = boto3.resource("dynamodb", region_name=config.AWS_REGION)

    # initialize the dynamodb table
    table = dynamodb.Table(ddb_table_name)

    # query the table for all items
    response = table.scan()
    repo_data = response["Items"]

    # extract the unique repository names
    repos = list(set(d["repo_name"] for d in repo_data))

    # initialize empty dictionaries to store the counts and uniques for each repository
    stat_counts = {repo: {"clones": 0, "views": 0} for repo in repos}
    type_uniques = {repo: {"clones": 0, "views": 0} for repo in repos}

    # iterate over the data and aggregate the counts and uniques for each repository
    for d in repo_data:
        repo = d["repo_name"]
        stat_type = d["stat_type"]
        count = int(d["count"])
        uniques = int(d["uniques"])

        stat_counts[repo][stat_type] += count
        type_uniques[repo][d["stat_type"]] += uniques

    # extract the aggregated counts and uniques for each repository
    clones_counts = [stat_counts[repo]["clones"] for repo in repos]
    views_counts = [stat_counts[repo]["views"] for repo in repos]
    clones_uniques = [type_uniques[repo]["clones"] for repo in repos]
    views_uniques = [type_uniques[repo]["views"] for repo in repos]

    # set the x-axis tick labels to be the repository names
    x_labels = [repos.split("/")[1] for repos in repos]

    # set the width of each bar
    width = 0.2

    # compute the x-positions for each bar
    x_pos_clones_counts = np.arange(len(x_labels))
    x_pos_clones_uniques = x_pos_clones_counts + width
    x_pos_views_counts = x_pos_clones_counts + 2 * width
    x_pos_views_uniques = x_pos_clones_counts + 3 * width

    # plot the bar chart
    fig, ax = plt.subplots(figsize=(20, 8))
    ax.bar(
        x_pos_clones_counts,
        clones_counts,
        width=width,
        color="r",
        alpha=0.5,
        label="Clones",
    )
    ax.bar(
        x_pos_clones_uniques,
        clones_uniques,
        width=width,
        color="r",
        alpha=0.2,
        label="Unique Clones",
    )
    ax.bar(
        x_pos_views_counts,
        views_counts,
        width=width,
        color="b",
        alpha=0.5,
        label="Views",
    )
    ax.bar(
        x_pos_views_uniques,
        views_uniques,
        width=width,
        color="b",
        alpha=0.2,
        label="Unique Views",
    )
    ax.set_ylabel("Count", wrap=True)
    ax.set_xlabel("Repository Name", wrap=True, fontsize=14, weight='bold', color='blue')
    ax.set_title("GitHub Repository Stats", wrap=True, fontsize=14, weight='bold', color='blue')

    # add a legend
    ax.legend()

    # set the tick labels and positions for the x-axis
    ax.set_xticks(x_pos_clones_counts + 1.5 * width)
    ax.set_xticklabels(x_labels, wrap=True, rotation=30, ha="right")
    ax.tick_params(axis="x", which="major", labelsize=8)

    # adjust the layout to fit the legend
    plt.subplots_adjust(right=0.85, left=0.1, bottom=0.3)
    plt.savefig(config.OUTPUT_FILE)

    # open the image in the default browser
    file_uri = 'file:///' + config.OUTPUT_FILE
    print(f"Saving the current data visualization to...{config.OUTPUT_FILE}")
    print("Opening a local browser to view the saved file..")
    webbrowser.open_new_tab(file_uri)


def list_github_repos(ddb_table_name):
    # initialize the dynamodb resource
    dynamodb = boto3.resource("dynamodb", region_name=config.AWS_REGION)

    # initialize the dynamodb table
    table = dynamodb.Table(ddb_table_name)

    # query the table for all items
    response = table.scan()
    repo_data = response["Items"]

    # extract the unique repository names
    repos = list(set(d["repo_name"] for d in repo_data))

    # Create a new table
    table = Table(show_header=True, header_style="bold blue")

    # Add the columns to the table
    table.add_column("Index", justify="left")
    table.add_column("GitHub Repositories", justify="left")

    # Add the data to the table
    for i, repo in enumerate(repos):
        table.add_row(str(i + 1), repo)

    # Print the table to the console
    console.print(table)


def print_usage():
    print(f"Usage: python3 {config.PROGRAM_NAME} [options]")
    print("Options:")
    print("\t--list\t\tList the GitHub repositories")
    print("\t--update\tUpdate the GitHub repository stats")
    print("\t--run\t\tRun the data visualization")
    print("\t--help\t\tPrint this help message")


if __name__ == "__main__":
    if __name__ == "__main__":
        """
        Main function, parse command line arguments and run the appropriate function
        """
        if args.list:
            list_github_repos(config.DDB_TABLE_NAME)
        elif args.update:
            update_stats(config.LAMBDA_FUNCTION_NAME)
        elif args.run:
            visualize_data(config.DDB_TABLE_NAME)
        else:
            print_usage()
