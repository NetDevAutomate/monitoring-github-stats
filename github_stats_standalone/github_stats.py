#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import logging
import webbrowser
from datetime import datetime, timedelta

import dash
import dash_bootstrap_components as dbc
import gunicorn.app.base
import plotly.graph_objs as go
import psutil
import requests
import yaml
from dash import dcc, html
from flask import Flask
from github import Github
from werkzeug.middleware.proxy_fix import ProxyFix

app_name = "GitHub Stats App"

access_token = os.environ["GITHUB_TOKEN"]
org_name = os.environ["GITHUB_ORG_NAME"]
team_name = os.environ["GITHUB_TEAM_NAME"]

base_url = "https://api.github.com/repos/"
base_dir = os.path.dirname(os.path.realpath(__file__))
repo_yaml_file = f"{base_dir}/repo.yaml"
log_dir = f"{base_dir}/logs"
data_directory = "./traffic_stats"
pid_file = f"{log_dir}/app.pid"
access_log = f"{log_dir}/access.log"
error_log = f"{log_dir}/error.log"

directory_list = [log_dir, data_directory]
debug = True

# Create command-line argument parser and define arguments
parser = argparse.ArgumentParser(
    description=f"{app_name}",
)

action_group = parser.add_mutually_exclusive_group(required=False)
action_group.add_argument("--create", "-c", action="store_true", help="Create a repo list YAML file")
action_group.add_argument("--run", "-r", action="store_true", help="Run Flask App and open browser")
action_group.add_argument("--update", "-u", action="store_true", help="Update repo list and stats")
action_group.add_argument("--shutdown", "-s", action="store_true", help="Shutdown Flask App")
action_group.add_argument("--list", "-l", action="store_true", help="List Repos")

control_group = parser.add_argument_group("control options")
control_group.add_argument("--daemon", "-d", action="store_true", help="Run as a daemon")


args = parser.parse_args()


class StandaloneApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


def create_app(repos_config):
    repos = parse_repo_config_file(repos_config)
    flask_app = Flask(__name__)
    # dash_app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    dash_app = dash.Dash(__name__, server=flask_app, url_base_pathname="/")

    dash_app.layout = html.Div(
        [
            html.H1(f"{app_name}",
                    style={'textAlign': 'center', 'color': '#2986cc'}
                    ),
            dbc.Container(
                [
                    html.Div([create_chart(repo, "views", fetch_traffic_stats(repo, "views"))])
                    for repo in repos
                ]
            ),
            dbc.Container(
                [
                    html.Div([create_chart(repo, "clones", fetch_traffic_stats(repo, "clones"))])
                    for repo in repos
                ]
            ),
        ]
    )

    return flask_app, dash_app


# Helper functions
def create_path_if_missing(path):
    """
    Creates any missing directories or files in the given path
    """
    if not os.path.exists(path):
        # Split path into directories and filename
        path_directories, path_file = os.path.split(path)

        # Recursively create missing directories
        if not os.path.exists(path_directories):
            os.makedirs(path_directories)

        # Create missing file
        open(path, "a").close()


# Functions to read and write to the repo_yaml_file
def create_repo_list(repo_config):
    """
    Creates a YAML file containing a list of all repos in the org
    """
    repos = get_all_repos()
    repo_dict = {}

    for repo in repos:
        key, value = repo.split("/")
        if key not in repo_dict:
            repo_dict[key] = []
        repo_dict[key].append(value)

    repo_dict_sorted = {k: sorted(v) for k, v in repo_dict.items()}
    yaml_doc = yaml.dump(repo_dict_sorted, sort_keys=True)

    with open(repo_config, "w") as f:
        f.write("---\n")
        f.write(yaml_doc)

    print(f"Created {repo_config}")

    return yaml_doc


def parse_repo_config_file(repo_config_file):
    """
    Read and parse the repo_yaml_file
    """
    with open(repo_config_file) as file:
        repos_yaml = yaml.safe_load(file)

    parsed_repo_list = []
    for key in repos_yaml.keys():
        for repo in repos_yaml[key]:
            parsed_repo_list.append(f"{key}/{repo}")

    return parsed_repo_list


# Function to get all repos in a team
def get_all_repos():
    """
    Fetches a list of all repos in the org
    """
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


def list_github_repos(repo_config_file):
    """
    Prints a list of all repos in the repo_yaml_file
    """
    repos = parse_repo_config_file(repo_config_file)
    for repo in repos:
        print(repo)


# Function to fetch traffic stats from GitHub API
def fetch_traffic_stats(repo, stat_type):
    """
    Fetch stats for the stat type from the repo's GitHub API endpoint
    """
    url = f"{base_url}{repo}/traffic/{stat_type}"
    headers = {"Authorization": f"token {access_token}"}

    data_file_path = os.path.join(data_directory, f"{repo}_{stat_type}.json")
    create_path_if_missing(data_file_path)

    if os.path.exists(data_file_path) and os.path.getsize(data_file_path) > 0:
        with open(data_file_path, "r") as f:
            loaded_data = json.load(f)
            data = {
                stat_type: {
                    item["timestamp"]: {"count": item["count"], "uniques": item["uniques"]}
                    for item in loaded_data[stat_type]
                }
            }
    else:
        data = {}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        new_data = response.json()

        if stat_type not in data:
            data[stat_type] = {
                item["timestamp"]: {"count": item["count"], "uniques": item["uniques"]}
                for item in new_data[stat_type]
            }
        else:
            for item in new_data[stat_type]:
                timestamp = item["timestamp"]
                if timestamp not in data[stat_type]:
                    data[stat_type][timestamp] = {
                        "count": item["count"],
                        "uniques": item["uniques"],
                    }
                else:
                    data[stat_type][timestamp]["count"] += item["count"]
                    data[stat_type][timestamp]["uniques"] += item["uniques"]

        # Convert the dictionary back to the original list structure before saving to the JSON file
        output_data = {
            stat_type: [
                {"timestamp": k, "count": v["count"], "uniques": v["uniques"]}
                for k, v in data[stat_type].items()
            ]
        }

        with open(data_file_path, "w") as f:
            json.dump(output_data, f)

        return output_data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {stat_type} data for {repo}: {e}")
        return data





# Dash functions
def create_chart(repo, stat_type, data):
    """
    Dash function to create a chart for the given repo and stat type
    """
    timestamps = []
    for item in data[stat_type]:
        print(item)
        if "timestamp" in item:
            try:
                timestamp = datetime.strptime(item["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                timestamps.append(timestamp)
            except ValueError:
                print(f"Invalid timestamp format for item: {item}")
        else:
            print(f"Timestamp key not found for item: {item}")
            continue

    counts = [item["count"] for item in data[stat_type]]
    uniques = [item["uniques"] for item in data[stat_type]]

    chart = go.Bar(
        x=timestamps,
        y=counts,
        name="Total",
        marker_color="rgba(75, 192, 192, 0.5)",
        marker_line_color="rgba(75, 192, 192, 1)",
        marker_line_width=1,
    )

    unique_chart = go.Bar(
        x=timestamps,
        y=uniques,
        name="Unique",
        marker_color="rgba(255, 99, 132, 0.5)",
        marker_line_color="rgba(255, 99, 132, 1)",
        marker_line_width=1,
    )

    # Calculate dynamic x-axis range based on data
    x_range = [min(timestamps) - timedelta(days=1), max(timestamps) + timedelta(days=1)]

    layout = go.Layout(
        title=f"{repo} - {stat_type}",
        xaxis=dict(title="Date", type="date", range=x_range),
        yaxis=dict(title="Count", rangemode="tozero"),
        barmode="group",
    )

    return dcc.Graph(figure={"data": [chart, unique_chart], "layout": layout})


# Function to get the latest data for all repos
def update_stats(repo_config_file):
    """
    Fetches the latest traffic stats for all repos in the repo_yaml_file
    """
    create_repo_list(repo_config_file)
    repos = parse_repo_config_file(repo_config_file)

    for repo in repos:
        print(f"Fetching data for {repo}...")
        fetch_traffic_stats(repo, "views")
        fetch_traffic_stats(repo, "clones")


def run_dash_app():
    """
    Sets up logging and runs the Dash/Flask app
    """

    # Check for the existence of the repo_yaml_file
    if not os.path.exists(repo_yaml_file):
        print(f"Repo YAML file not found: {repo_yaml_file}")
        print("Creating repo YAML file...")
        create_repo_list(repo_yaml_file)
        print(f"Repo YAML file created: {repo_yaml_file}")

    flask_app, dash_app = create_app(repo_yaml_file)
    log_handler = logging.StreamHandler()
    log_handler.setLevel(logging.INFO)
    flask_app.logger.addHandler(log_handler)
    flask_app = ProxyFix(flask_app, x_proto=1, x_host=1)

    # Flask server options
    server_options = {
        "bind": "0.0.0.0:8050",
        "workers": 2,
        "log-level": "debug",
        "accesslog": access_log,
        "errorlog": error_log,
        "pidfile": pid_file,
    }
    StandaloneApplication(flask_app, server_options).run()


# Check if process is running
def is_process_running(pid):
    """
    Checks if a process is running
    """
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_RUNNING:
            return True
    except psutil.NoSuchProcess:
        pass
    return False


# Kill process
def kill_process(pid):
    """
    Kills a process by PID
    """
    try:
        process = psutil.Process(pid)
        process.terminate()
    except psutil.NoSuchProcess:
        pass


# Check if directories exist and create them if not
def check_dirs(directories):
    """
    Creates any missing directories or files in the given path.
    """
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)


# Run the Dash app and open it in a web browser or shut it down
def run_and_display(shutdown):
    """
    Runs the Dash app and opens it in a web browser or shuts it down
    """
    check_dirs(directory_list)

    # Shuts down the Dash app if it's already running
    if shutdown:
        print("Shutting down Dash app...")
        with open(pid_file, "r") as f:
            pid = int(f.read())
        kill_process(pid)
        return

    # Start the Dash app as a background process
    print("Starting GitHub Stats App...")
    cmd = ["python3", "github_stats.py", "--daemon"]
    proc = subprocess.Popen(cmd)

    # Wait for the app to start
    time.sleep(10)

    # Open the app in a web browser
    print("Opening Dash app in web browser...")
    webbrowser.open_new("http://127.0.0.1:8050/")

    # Write process PID to file
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))


def display_usage():
    print("Usage: github_stats.py [options]")
    print("Options:")
    print("  -h, --help\t\t\tDisplay this help message")
    print("  -l, --list\t\t\tList all repos in the repo YAML file")
    print("  -u, --update\t\t\tUpdate the stats for all repos in the repo YAML file")
    print("  -r, --run\t\t\tRun the Dash app")
    print("  -s, --shutdown\t\t\tShutdown the Dash app")
    print("  -c, --create\t\t\tCreate the repo YAML file")
    sys.exit(1)


if __name__ == "__main__":
    """
    Main function, parse command line arguments and run the appropriate function
    """
    if args.list:
        list_github_repos(repo_yaml_file)
    elif args.update:
        update_stats(repo_yaml_file)
    elif args.run:
        run_and_display(shutdown=False)
    elif args.shutdown:
        run_and_display(shutdown=True)
    elif args.create:
        create_repo_list(repo_yaml_file)
    elif args.daemon:
        run_dash_app()
    else:
        display_usage()
