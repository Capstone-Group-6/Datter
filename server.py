import csv
from io import StringIO
from pathlib import Path
from typing import Iterable

import aiohttp_jinja2
import jinja2
from aiohttp import web
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def setup_db() -> AsyncIOMotorDatabase:
	db = AsyncIOMotorClient().datter
	first_dataset = await db.datasets.find_one({})
	if not first_dataset:
		await db.datasets.insert_one({'title': "sample.csv", 'columns': ["message", "explanation"], 'data': [{'message': "Welcome to Datter!", 'explanation': "This is a demonstration of the progress that we have made on Datter."}]})
	return db


routes = web.RouteTableDef()

routes.static(prefix="/static", path=Path.cwd() / "static")


@routes.get("/")
async def index_page(request: web.Request) -> web.Response:
	db = request.app["db"]
	datasets = []
	async for dataset in db.datasets.find({}):
		datasets.append({'url': f"/data/{str(dataset['_id'])}", 'title': dataset['title']})
	
	return aiohttp_jinja2.render_template("index.jinja2", request, context={'datasets': datasets})


@routes.get('/data/{id}')
async def read_data(request: web.Request) -> web.Response:
	dataset_id = request.match_info.get("id")
	
	db = request.app["db"]
	dataset = await db.datasets.find_one(ObjectId(dataset_id))
	if not dataset:
		raise web.HTTPNotFound()
	
	context = {'title': dataset['title'], 'columns': dataset['columns'], 'data': dataset['data']}
	
	return aiohttp_jinja2.render_template("dataset.jinja2", request, context=context)


def read_dataset_from_string(title: str, lines: Iterable[str]) -> dict:
	dataset = {'title': title}
	reader = csv.DictReader(lines)
	columns = None
	data = []
	
	for row in reader:
		if columns is None:
			columns = [k for k in row.keys()]
		data.append(row)
	
	dataset['columns'] = columns
	dataset['data'] = data
	return dataset


@routes.post("/data")
async def submit_data(request: web.Request) -> web.Response:
	db = request.app["db"]
	form_reader = await request.multipart()
	
	field = await form_reader.next()
	csv_text = await field.text()
	with StringIO(csv_text) as str_in:
		dataset = read_dataset_from_string(field.filename, str_in)
	
	dataset_id = await db.datasets.insert_one(dataset)
	return web.json_response({'redirect_to': f"/data/{str(dataset_id.inserted_id)}"})


async def create_app():
	global routes
	app_db = await setup_db()
	
	app = web.Application()
	aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./views'))
	
	app["db"] = app_db
	app.add_routes(routes)
	return app


if __name__ == '__main__':
	web.run_app(create_app())
