import json
from pathlib import Path


def entry(app: dict):
	return {
		"name": app['name'],
		"icon": app['icon'],
		"store_info": app['store_info'],
	}


app_dir = Path(__file__).parent / 'apps'

all_apps_json = {
	"apps": list(entry(json.loads((a / 'app.json').read_text())) for a in app_dir.glob('*'))
}

store_metadata_file = Path(__file__).parent / 'apps' / 'store_metadata.json'
store_metadata_file.write_text(json.dumps(all_apps_json, indent=2))
