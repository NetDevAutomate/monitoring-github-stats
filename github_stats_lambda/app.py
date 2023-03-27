#!/usr/bin/env python3
import os
import platform
from aws_cdk import App, Environment

from src.github_stats_cdk_stack import GithubStatsCdkStack

platform = platform.machine()

access_token = os.environ["GITHUB_TOKEN"]
org_name = os.environ["GITHUB_ORG_NAME"]
team_name = os.environ["GITHUB_TEAM_NAME"]
account = os.environ["CDK_DEFAULT_ACCOUNT"]
region = os.environ["CDK_DEFAULT_REGION"]

app = App()
GithubStatsCdkStack(
    app,
    "GithubStatsCdkStack",
    org_name=org_name,
    team_name=team_name,
    access_token=access_token,
    platform=platform,
    env=Environment(account=account, region=region),
)

app.synth()
