import asyncio
import csv
from collections import namedtuple
from io import StringIO
from pathlib import Path
from typing import Iterable, Optional

import aiohttp_jinja2
import aiohttp_session
import jinja2
from aiohttp import web
from aiohttp_session import get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def setup_db() -> AsyncIOMotorDatabase:
	db = AsyncIOMotorClient().datter
	return db


DataSet = namedtuple("DataSet", ["title", "owner", "columns", "data"])


async def get_dataset(db: AsyncIOMotorDatabase, dataset_id: str) -> DataSet:
	dataset = await db.datasets.find_one(ObjectId(dataset_id))
	data_rows = []
	
	async for data_row in db.data_rows.find({'dataset': dataset_id}):
		data_rows.append(data_row['datum'])
	
	return DataSet(dataset['title'], dataset['owner'], dataset['columns'], data_rows)


async def put_dataset(db: AsyncIOMotorDatabase, dataset: DataSet) -> str:
	metadata = {'title': dataset.title, 'owner': dataset.owner, 'columns': dataset.columns}
	dataset_id = (await db.datasets.insert_one(metadata)).inserted_id
	
	rows_to_insert = [{'dataset': str(dataset_id), 'datum': datum} for datum in dataset.data]
	await asyncio.gather(*[db.data_rows.insert_one(row) for row in rows_to_insert])
	
	return str(dataset_id)


# might add more data later
UserInfo = namedtuple("UserInfo", ["id", "username"])
Argon2 = PasswordHasher()


async def get_logged_in(request: web.Request) -> Optional[UserInfo]:
	session = await get_session(request)
	if "user_id" not in session:
		return None
	
	user_id = session["user_id"]
	if not user_id:
		return None
	
	user_data = await request.app["db"].users.find_one(ObjectId(user_id))
	if not user_data:
		# If the user doesn't exist, force the session to log out
		del session["user_id"]
		return None
	
	return UserInfo(user_id, user_data['username'])


async def set_logged_in(request: web.Request, user_id: Optional[str]):
	session = await get_session(request)
	session["user_id"] = user_id


routes = web.RouteTableDef()
routes.static(prefix="/static", path=Path.cwd() / "static")


@routes.get("/")
async def index_page(request: web.Request) -> web.Response:
	logged_in_as = await get_logged_in(request)
	if not logged_in_as:
		# Redirect to login page
		raise web.HTTPFound("/login")
	
	db = request.app["db"]
	datasets = []
	async for dataset in db.datasets.find({'owner': logged_in_as.id}):
		datasets.append({'url': f"/data/{str(dataset['_id'])}", 'title': dataset['title']})
	
	return aiohttp_jinja2.render_template("index.jinja2", request, context={'datasets': datasets, 'username': logged_in_as.username})


@routes.get("/help")
async def help_page(request: web.Request) -> web.Response:
	logged_in_as = await get_logged_in(request)
	if not logged_in_as:
		# Redirect to login page
		raise web.HTTPFound("/login")
	
	db = request.app["db"]
	datasets = []
	async for dataset in db.datasets.find({'owner': logged_in_as.id}):
		datasets.append({'url': f"/data/{str(dataset['_id'])}", 'title': dataset['title']})
	
	return aiohttp_jinja2.render_template("help.jinja2", request, context={'datasets': datasets, 'username': logged_in_as.username})


@routes.get("/recall-data")
async def recall_data_page(request: web.Request) -> web.Response:
	return aiohttp_jinja2.render_template("recalldata.jinja2", request, context={})


@routes.get("/create-account")
async def register_page(request: web.Request) -> web.Response:
	return aiohttp_jinja2.render_template("register.jinja2", request, context={})


@routes.get("/login")
async def login_page(request: web.Request) -> web.Response:
	return aiohttp_jinja2.render_template("login.jinja2", request, context={})


@routes.post("/create-account")
async def process_registration(request: web.Request) -> web.Response:
	db = request.app["db"]
	posted_data = await request.post()
	username = posted_data['username']
	if await db.users.find_one({'username': username}):
		return aiohttp_jinja2.render_template("register.jinja2", request, context={'error': "That user already exists"})
	
	password = Argon2.hash(posted_data['password'])
	
	user_creation = await db.users.insert_one({'username': username, 'password': password})
	await set_logged_in(request, str(user_creation.inserted_id))
	
	# Go to index page
	raise web.HTTPFound("/")


@routes.post("/login")
async def handle_login(request: web.Request) -> web.Response:
	db = request.app["db"]
	posted_data = await request.post()
	username = posted_data['username']
	
	db_user_data = await db.users.find_one({'username': username})
	if not db_user_data:
		return aiohttp_jinja2.render_template("login.jinja2", request, context={'error': "Incorrect credentials"})
	
	try:
		successful_login = Argon2.verify(db_user_data['password'], posted_data['password'])
	except VerificationError:
		successful_login = False
	
	if not successful_login:
		return aiohttp_jinja2.render_template("login.jinja2", request, context={'error': "Incorrect credentials"})
	
	await set_logged_in(request, str(db_user_data['_id']))
	
	# Go to index page
	raise web.HTTPFound("/")


@routes.post("/logout")
async def handle_logout(request: web.Request) -> web.Response:
	await set_logged_in(request, None)
	
	# Go to index page
	raise web.HTTPFound("/login")


@routes.get('/data/{id}')
async def read_data(request: web.Request) -> web.Response:
	get_user = get_logged_in(request)
	dataset_id = request.match_info.get("id")
	
	db = request.app["db"]
	dataset_metadata = await db.datasets.find_one(ObjectId(dataset_id))
	logged_in_as = await get_user
	
	if not logged_in_as:
		raise web.HTTPFound('/login')
	if not dataset_metadata:
		raise web.HTTPNotFound()
	if dataset_metadata['owner'] != logged_in_as.id:
		raise web.HTTPNotFound()
	
	dataset = await get_dataset(db, dataset_id)
	
	context = {'id': dataset_id, 'title': dataset.title, 'columns': dataset.columns, 'data': dataset.data, 'username': logged_in_as.username}
	
	return aiohttp_jinja2.render_template("dataset.jinja2", request, context=context)


@routes.get('/data/{id}/histogram/{column}')
async def view_histogram(request: web.Request) -> web.Response:
	get_user = get_logged_in(request)
	dataset_id = request.match_info.get("id")
	
	db = request.app["db"]
	dataset_metadata = await db.datasets.find_one(ObjectId(dataset_id))
	logged_in_as = await get_user
	
	if not logged_in_as:
		raise web.HTTPFound('/login')
	if not dataset_metadata:
		raise web.HTTPNotFound()
	if dataset_metadata['owner'] != logged_in_as.id:
		raise web.HTTPNotFound()
	
	dataset = await get_dataset(db, dataset_id)
	
	column = request.match_info.get("column")
	if column not in dataset.columns:
		column = dataset.columns[0]
	
	context = {'data_id': dataset_id, 'title': dataset.title, 'column': column, 'data': dataset.data, 'username': logged_in_as.username}
	
	response = aiohttp_jinja2.render_template("histogram.jinja2", request, context=context)
	return response


def read_dataset_from_string(title: str, lines: Iterable[str], user_id: str) -> DataSet:
	reader = csv.DictReader(lines)
	columns = reader.fieldnames
	data = []
	
	for row in reader:
		data.append(row)
	
	return DataSet(title, user_id, columns, data)


@routes.post("/data")
async def submit_data(request: web.Request) -> web.Response:
	logged_in_as = await get_logged_in(request)
	if not logged_in_as:
		raise web.HTTPFound("/login")
	
	db = request.app["db"]
	form_reader = await request.multipart()
	
	field = await form_reader.next()
	csv_text = await field.text()
	with StringIO(csv_text) as str_in:
		dataset = read_dataset_from_string(field.filename, str_in, logged_in_as.id)
	
	dataset_id = await put_dataset(db, dataset)
	return web.json_response({'redirect_to': f"/data/{str(dataset_id)}"})


async def create_app():
	global routes
	app_db = await setup_db()
	
	app = web.Application()
	aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./views'), extensions=['jinja2.ext.do'])
	# TODO This key is only for testing purposes, change it to an ENVIRONMENT VARIABLE (important!) for production
	aiohttp_session.setup(app, EncryptedCookieStorage(b'This is a secret key don\'t steal'))
	
	app["db"] = app_db
	app.add_routes(routes)
	return app


if __name__ == '__main__':
	web.run_app(create_app())
