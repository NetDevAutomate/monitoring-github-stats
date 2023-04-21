#!/usr/bin/env python3
import boto3
import matplotlib.pyplot as plt
import numpy as np

aws_region = "eu-west-1"
table_name = "github_stats"

# initialize the dynamodb resource
dynamodb = boto3.resource("dynamodb", region_name=aws_region)

# initialize the dynamodb table
table = dynamodb.Table(table_name)

# query the table for all items
response = table.scan()
data = response["Items"]

# extract the unique repository names
repos = list(set(d["repo_name"] for d in data))

# initialize empty dictionaries to store the counts and uniques for each repository
stat_counts = {repo: {"clones": 0, "views": 0} for repo in repos}
type_uniques = {repo: {"clones": 0, "views": 0} for repo in repos}

# iterate over the data and aggregate the counts and uniques for each repository
for d in data:
    repo = d["repo_name"]
    stat_type = d["stat_type"]
    count = int(d["count"])
    uniques = int(d["uniques"])

    stat_counts[repo][stat_type] += count
    type_uniques[repo][d["type"]] += uniques

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
# ax.set_xlabel("Repository Name", wrap=True)
ax.set_title("GitHub Repository Stats")

# add a legend
ax.legend()

# set the tick labels and positions for the x-axis
ax.set_xticks(x_pos_clones_counts + 1.5 * width)
ax.set_xticklabels(x_labels, wrap=True, rotation=30, ha="right")
ax.tick_params(axis="x", which="major", labelsize=8)

# adjust the layout to fit the legend
plt.subplots_adjust(right=0.85, left=0.1, bottom=0.3)
plt.show()
