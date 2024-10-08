#!/usr/bin/env python3
import argparse
import http.client
import itertools
import json
import re
from pathlib import Path
from typing import Literal

FILE_EXTENSIONS = ['yml.template', 'json', 'env']


# todo: handle version suffixes like with baikal. e.g. 0.1.2-nginx
# todo: also use the docker hub api to get the latest version of the image

def main(command: Literal['check', 'update', 'commit']):
	if command == 'check':
		print('=== Checking for updates, no files will be modified. ===')
	elif command == 'update':
		print('=== Updating files. ===')

	apps_dir = Path(__file__).parent / 'apps'
	apps_without_upstream = []
	apps_up_to_date = []
	for app_dir in sorted(apps_dir.iterdir()):
		if not app_dir.is_dir():
			continue

		current_version, latest_version = get_versions(app_dir)
		if latest_version is None:
			apps_without_upstream.append(app_dir.name)
			continue

		if current_version == latest_version:
			apps_up_to_date.append(app_dir.name)
			continue

		if command == 'update':
			for file_path in itertools.chain(*(app_dir.glob(f'**/*.{ext}') for ext in FILE_EXTENSIONS)):
				update_file(file_path, current_version, latest_version)
		print(f'{app_dir.name:<20} {current_version:<10}  ->  {latest_version}')

	print(f'{len(apps_without_upstream)} apps without upstream: {', '.join(apps_without_upstream)}')
	print(f'{len(apps_up_to_date)} apps up to date: {', '.join(apps_up_to_date)}')


def parse_args():
	parser = argparse.ArgumentParser(description='Update application versions.')
	parser.add_argument('command', type=str, choices=['check', 'update', 'commit'])
	return parser.parse_args()


def get_versions(app_dir: Path) -> tuple[str, str | None]:
	with open(app_dir / 'app_meta.json') as f:
		app_meta = json.load(f)

	if 'upstream_repo' not in app_meta:
		return app_meta['app_version'], None

	latest_version = adapt_version_string(app_dir.name, get_latest_version(app_meta['upstream_repo']))

	return app_meta['app_version'], latest_version


def get_latest_version(upstream_repo: str):
	gitlab_link_regex = r'https://github\.com/([^/]+)/([^/]+)'
	match = re.match(gitlab_link_regex, upstream_repo)
	owner = match.group(1)
	repo = match.group(2)

	conn = http.client.HTTPSConnection("api.github.com")

	headers = {
		'Accept': 'application/vnd.github+json',
		'X-GitHub-Api-Version': '2022-11-28',
		'User-Agent': 'Portal-App-Store'
	}

	url = f'/repos/{owner}/{repo}/releases'
	conn.request("GET", url, headers=headers)
	response = conn.getresponse()
	if response.status != 200:
		raise Exception(f'Failed to get releases from {url}: {response.status} {response.reason}')
	data = response.read()

	releases = json.loads(data)
	return releases[0]['tag_name']


def update_file(file_path: Path, current_version: str, latest_version: str):
	with open(str(file_path)) as f:
		content = f.read()

	content = content.replace(current_version, latest_version)

	with open(file_path, 'w') as f:
		f.write(content)


def adapt_version_string(app_name: str, version: str) -> str:
	new_version = version
	if app_name in ['actual', 'audiobookshelf', 'drawio', 'etherpad', 'kavita', 'linkding', 'navidrome',
					'paperless-ngx', 'stirling-pdf']:
		new_version = version[1:]  # remove the 'v' prefix
	if app_name in ['element']:
		new_version = version.split('-')[0]  # remove the suffix
	if app_name in ['glances']:
		new_version = version + '-full'  # add the '-full' suffix
	return new_version


if __name__ == '__main__':
	args = parse_args()
	main(args.command)
