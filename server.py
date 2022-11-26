import asyncio
import csv
import os
import re
from collections import namedtuple
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Iterable, Optional, Any

import aiohttp_jinja2
import aiohttp_session
import jinja2
from aiohttp import web
from aiohttp_session import get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from bson import ObjectId
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase


async def setup_db() -> AsyncIOMotorDatabase:
	db = AsyncIOMotorClient().datter
	return db


DataSet = namedtuple("DataSet", ["title", "owner", "columns", "data"])
DataTestResult = namedtuple("DataSet", ["columns", "data", "mean", "std_dev"])

DATE_REGEX = re.compile("([0-9]{4})-([0-9]{2})-([0-9]{2})")


def convert_to_date(text: str) -> Optional[datetime]:
	date_test = DATE_REGEX.fullmatch(text)
	if not date_test:
		return None
	y, m, d = [int(i) for i in date_test.groups()]
	return datetime(y, m, d)


async def get_dataset(db: AsyncIOMotorDatabase, dataset_id: str) -> DataSet:
	dataset = await db.datasets.find_one(ObjectId(dataset_id))
	data_rows = []
	
	async for data_row in db.data_rows.find({'dataset': dataset_id}):
		data_rows.append(data_row['datum'])
	
	return DataSet(dataset['title'], dataset['owner'], dataset['columns'], data_rows)


async def test_dataset(db: AsyncIOMotorDatabase, test: str, username: str, start_date: datetime, end_date: datetime) -> Optional[DataTestResult]:
	data_cols = set()
	data_rows = []
	
	# Statistics
	results = []
	num_rows = 0
	
	async for data_row in db.data_rows.find({'datum.Results': {'$exists': True}, 'datum.Date': {'$gte': start_date, '$lte': end_date}, 'datum.User': username, 'datum.Test': test}):
		datum = data_row['datum']
		data_cols.update(datum.keys())
		data_rows.append(datum)
		
		results.append(float(datum['Results']))
		num_rows += 1
	
	if num_rows == 0:
		return None
	
	mean = sum(results) / num_rows
	# TODO - we need to know for certain if we should be using Bessel's correction here
	std_dev = (sum((i - mean) ** 2 for i in results) / (num_rows - 1)) ** 0.5
	
	return DataTestResult(data_cols, data_rows, mean, std_dev)


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
	logged_in_as = await get_logged_in(request)
	if not logged_in_as:
		# Redirect to login page
		raise web.HTTPFound("/login")
	
	return aiohttp_jinja2.render_template("recalldata.jinja2", request, context={'username': logged_in_as.username})


@routes.post("/recall-data")
async def process_recall_data(request: web.Request) -> web.Response:
	db = request.app["db"]
	logged_in_as = await get_logged_in(request)
	if not logged_in_as:
		raise web.HTTPFound("/login")
	
	posted_form = await request.post()
	
	username = posted_form['username'].lower()
	test = posted_form['test'].lower()
	
	start_date = convert_to_date(posted_form['FirstTest'])
	if not start_date:
		return aiohttp_jinja2.render_template("recalldata.jinja2", request, context={'error': "Invalid format for First Test Date - please use the calendar input"})
	
	end_date = convert_to_date(posted_form['FinalTest'])
	if not end_date:
		return aiohttp_jinja2.render_template("recalldata.jinja2", request, context={'error': "Invalid format for Final Test Date - please use the calendar input"})
	
	test_results = await test_dataset(db, test, username, start_date, end_date)
	if not test_results:
		return aiohttp_jinja2.render_template("recalldata.jinja2", request, context={'error': "No rows found - are you sure you entered in your query correctly?"})
	
	return aiohttp_jinja2.render_template("recalldata_results.jinja2", request, context={'columns': test_results.columns, 'data': test_results.data, 'mean': test_results.mean, 'std_dev': test_results.std_dev, 'username': logged_in_as.username})


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
	
	if not username or username.isspace():
		return aiohttp_jinja2.render_template("register.jinja2", request, context={'error': "Invalid username, must contain non-whitespace characters"})
	
	if await db.users.find_one({'username': username}):
		return aiohttp_jinja2.render_template("register.jinja2", request, context={'error': "That user already exists"})
	
	if not posted_data['password']:
		return aiohttp_jinja2.render_template("register.jinja2", request, context={'error': "Invalid password, must not be blank"})
	
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
	
	if not username or username.isspace():
		return aiohttp_jinja2.render_template("login.jinja2", request, context={'error': "Invalid username, must contain non-whitespace characters"})
	
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


def process_cell(cell_data: str) -> Any:
	# Check if it's a date
	date_test = convert_to_date(cell_data)
	if date_test:
		return date_test
	
	# Check if it's a float
	try:
		return float(cell_data)
	except ValueError:
		pass
	
	return cell_data.lower()


def read_dataset_from_string(title: str, lines: Iterable[str], user_id: str) -> DataSet:
	reader = csv.DictReader(lines)
	columns = reader.fieldnames
	data = []
	
	for row in reader:
		processed_row = {k: process_cell(v) for (k, v) in row.items()}
		data.append(processed_row)
	
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
	aiohttp_session.setup(app, EncryptedCookieStorage(bytes.fromhex(os.environ["DATTER_SECRET_KEY"])))
	
	app["db"] = app_db
	app.add_routes(routes)
	return app


if __name__ == '__main__':
	load_dotenv()
	web.run_app(create_app())
