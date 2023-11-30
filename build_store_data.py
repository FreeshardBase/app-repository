#!/usr/bin/env python3

import json
import zipfile
from pathlib import Path

app_dir = Path(__file__).parent / 'apps'


def _make_metadata_entry(app_path: Path):
	with open(app_path / 'app_meta.json') as f:
		app_meta = json.load(f)
	return {
		"name": app_meta['name'],
		"icon": app_meta['icon'],
		"minimum_portal_size": app_meta.get('minimum_portal_size', 'xs'),
		"store_info": app_meta['store_info'],
	}


def write_store_metadata():
	all_apps_json = {
		"apps": list(_make_metadata_entry(a) for a in app_dir.glob('*') if a.is_dir())
	}

	store_metadata_file = app_dir / 'store_metadata.json'
	with open(store_metadata_file, 'w') as f:
		json.dump(all_apps_json, f, indent=2)


def make_app_zips():
	for app_path in app_dir.glob('*'):
		if not app_path.is_dir():
			continue
		zip_file = app_path / f'{app_path.name}.zip'
		print(f'creating zip for {zip_file}')
		zip_file.unlink(missing_ok=True)
		with zipfile.ZipFile(zip_file, 'w') as z:
			for p in app_path.glob('**/*'):
				if p.is_dir():
					continue
				if p.name == zip_file.name:
					continue
				z.write(p, p.relative_to(app_path))


if __name__ == '__main__':
	write_store_metadata()
	make_app_zips()
