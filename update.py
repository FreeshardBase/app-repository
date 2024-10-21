#!/usr/bin/env python3
import argparse
import http.client
import itertools
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict, Tuple

from build_store_data import make_app_zips

UPDATE_INFO_JSON = Path(__file__).parent / 'update_info' / 'update_info.json'
GITHUB_TOKEN_FILE = Path(__file__).parent / 'update_info' / 'github_token'
UPDATED_APPS_DIR = Path(__file__).parent / 'update_info' / 'updated_apps'
FILE_EXTENSIONS = ['yml.template', 'json', 'env']


# todo: handle version suffixes like with baikal. e.g. 0.1.2-nginx
# todo: also use the docker hub api to get the latest version of the image


class AppInfo(TypedDict):
	status: Literal['no_upstream', 'up_to_date', 'outdated', 'updated']
	current_version: str
	latest_version: str | None
	breaking_changes: list[Tuple[str, str]]


class UpdateInfo(TypedDict):
	timestamp: str
	apps: dict[str, AppInfo]


def main(command: Literal['check', 'update', 'test', 'commit']):
	UPDATE_INFO_JSON.parent.mkdir(exist_ok=True)
	if command == 'check':
		command_check()
	if command == 'update':
		command_update()
	if command == 'test':
		command_test()
	if command == 'commit':
		command_commit()


def command_check():
	# check for update_info.json file and prompt if it should be overwritten
	do_update = True
	if UPDATE_INFO_JSON.exists():
		overwrite = input(f'update_info.json already exists. Overwrite? (y/n): ')
		if overwrite.lower() != 'y':
			do_update = False

	if do_update:
		print('=== Checking for updates, no app files will be modified. ===')
		apps_dir = Path(__file__).parent / 'apps'
		update_info = UpdateInfo(timestamp=datetime.now(timezone.utc).isoformat(), apps={})
		for app_dir in sorted(apps_dir.iterdir()):
			if not app_dir.is_dir():
				continue
			update_info['apps'][app_dir.name] = make_app_info(app_dir)
			print('.', end='', flush=True)
		print('\r', end='', flush=True)

		with open(UPDATE_INFO_JSON, 'w') as f:
			json.dump(update_info, f, indent=2)

	print_update_info()
	print(f'=== Run the update command to update the outdated apps. ===')


def command_update():
	if not UPDATE_INFO_JSON.exists():
		print('Run the check command first to create the update_info.json file.')
		exit(1)

	print('=== Updating app files. ===')
	with open(UPDATE_INFO_JSON) as f:
		update_info: UpdateInfo = json.load(f)

	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'outdated':
			app_dir = Path(__file__).parent / 'apps' / app_name
			for file_path in itertools.chain(*(app_dir.glob(f'**/*.{ext}') for ext in FILE_EXTENSIONS)):
				update_file(file_path, app_info['current_version'], app_info['latest_version'])
			app_info['status'] = 'updated'
			print(f'Updated {app_name:<20} {app_info["current_version"]:<10}  ->  {app_info["latest_version"]}')

	make_app_zips()
	UPDATED_APPS_DIR.mkdir(exist_ok=True)
	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'updated':
			app_dir = Path(__file__).parent / 'apps' / app_name
			shutil.copy(app_dir / f'{app_name}.zip', UPDATED_APPS_DIR / f'{app_name}.zip')

	with open(UPDATE_INFO_JSON, 'w') as f:
		json.dump(update_info, f, indent=2)

	print(
		f'=== Done updating app files. Smoke test the apps in "update_info/updated_apps", then run the commit command. ===')


def command_test():
	if not UPDATE_INFO_JSON.exists():
		print('Run the check command first to create the update_info.json file.')
		exit(1)

	print('=== Testing if updated apps can be pulled. ===')
	with open(UPDATE_INFO_JSON) as f:
		update_info: UpdateInfo = json.load(f)

	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'updated':
			app_dir = Path(__file__).parent / 'apps' / app_name
			shutil.copy(app_dir / 'docker-compose.yml.template', app_dir / 'docker-compose.yml')
			update_file(app_dir / 'docker-compose.yml', '{{ fs.app_data }}', './app_data', '{{ fs.shared }}',
						'./shared')

			pull_process = subprocess.Popen(['docker-compose', 'pull', '--dry-run', '-q'], cwd=app_dir)
			if pull_process.wait() == 0:
				print(f'Pulling {app_name} seems to work.')
			else:
				print(f'!!! Failed to pull {app_name} !!!')

			(app_dir / 'docker-compose.yml').unlink()


def command_commit():
	print('=== Committing changes. ===')
	if not UPDATE_INFO_JSON.exists():
		print('Run the check command first to create the update_info.json file.')
		exit(1)

	with open(UPDATE_INFO_JSON) as f:
		update_info: UpdateInfo = json.load(f)

	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'updated':
			commit_message = f'Update {app_name} from {app_info['current_version']} to {app_info['latest_version']}'
			subprocess.run(['git', 'add', f'apps/{app_name}'])
			subprocess.run(['git', 'commit', '-m', commit_message])
			print(f'Committed changes for {app_name}')

	UPDATE_INFO_JSON.unlink()


def parse_args():
	parser = argparse.ArgumentParser(description='Update application versions.')
	parser.add_argument('command', type=str, choices=['check', 'update', 'test', 'commit'])
	return parser.parse_args()


def make_app_info(app_dir: Path) -> AppInfo:
	with open(app_dir / 'app_meta.json') as f:
		app_meta = json.load(f)

	app_name = app_dir.name
	current_version = app_meta['app_version']
	result = AppInfo(status='no_upstream', current_version=current_version, latest_version=None, breaking_changes=[])

	if 'upstream_repo' not in app_meta:
		return result

	latest_releases = get_latest_releases(app_meta['upstream_repo'], current_version)
	if latest_releases:
		result.update(status='outdated', latest_version=adapt_version_string(app_name, latest_releases[0]['tag_name']))
		result.update(breaking_changes=[(release['tag_name'], release['html_url']) for release in latest_releases if
										'breaking' in release['body'].lower()])
	else:
		result.update(status='up_to_date', latest_version=current_version)

	return result


def get_latest_releases(upstream_repo: str, current_version: str):
	github_link_regex = r'https://github\.com/([^/]+)/([^/]+)'
	match = re.match(github_link_regex, upstream_repo)
	owner = match.group(1)
	repo = match.group(2)

	conn = http.client.HTTPSConnection("api.github.com")

	headers = {
		'Accept': 'application/vnd.github+json',
		'X-GitHub-Api-Version': '2022-11-28',
		'User-Agent': 'Portal-App-Store'
	}

	if GITHUB_TOKEN_FILE.exists():
		with open(GITHUB_TOKEN_FILE) as f:
			token = f.read().strip()
		headers['Authorization'] = f'token {token}'

	url = f'/repos/{owner}/{repo}/releases'
	conn.request("GET", url, headers=headers)
	response = conn.getresponse()
	if response.status != 200:
		if response.status == 403 and response.reason == 'rate limit exceeded':
			print('Rate limit exceeded. Try again later or consider using a personal access token.')
			print('You can generate it here: https://github.com/settings/tokens.')
			print('Place it in the file update_info/github_token.')
			exit(1)
		raise Exception(f'Failed to get releases from {url}: {response.status} {response.reason}')
	data = response.read()

	releases = json.loads(data)
	result = []
	for release in releases:
		if release['tag_name'] != current_version:
			result.append(release)
		else:
			break

	return result


def update_file(file_path: Path, *replacements: str):
	replacements_iter = iter(replacements)
	with open(str(file_path)) as f:
		content = f.read()

	for a, b in itertools.batched(replacements_iter, 2):
		content = content.replace(a, b)

	with open(file_path, 'w') as f:
		f.write(content)


def adapt_version_string(app_name: str, version: str) -> str:
	new_version = version
	if app_name in ['actual', 'audiobookshelf', 'drawio', 'etherpad', 'kavita', 'linkding', 'navidrome',
					'paperless-ngx', 'stirling-pdf', 'grist']:
		new_version = version[1:]  # remove the 'v' prefix
	if app_name in ['element']:
		new_version = version.split('-')[0]  # remove the suffix
	if app_name in ['glances']:
		new_version = version + '-full'  # add the '-full' suffix
	return new_version


def print_update_info():
	with open(UPDATE_INFO_JSON) as f:
		update_info: UpdateInfo = json.load(f)
	print(f'=== Checked {len(update_info['apps'])} apps on {update_info["timestamp"]} ===')
	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'outdated':
			breaking = f'({len(app_info['breaking_changes'])} possible breaking changes: {', '.join([c[0] for c in app_info['breaking_changes']])})' if \
			app_info['breaking_changes'] else ''
			print(f'{app_name:<20} {app_info["current_version"]:<10}  ->  {app_info["latest_version"]:<10} {breaking}')
	apps_without_upstream = [app_name for app_name, app_info in update_info['apps'].items() if
							 app_info['status'] == 'no_upstream']
	print(f'{len(apps_without_upstream)} apps without upstream: {', '.join(apps_without_upstream)}')
	apps_up_to_date = [app_name for app_name, app_info in update_info['apps'].items() if
					   app_info['status'] == 'up_to_date']
	print(f'{len(apps_up_to_date)} apps up to date: {', '.join(apps_up_to_date)}')

	print('')
	for app_name, app_info in update_info['apps'].items():
		if app_info['status'] == 'outdated' and app_info['breaking_changes']:
			print(f'--- Breaking changes for {app_name} ---')
			for version, url in app_info['breaking_changes']:
				print(f'{version}: {url}#:~:text=breaking')


if __name__ == '__main__':
	args = parse_args()
	main(args.command)
