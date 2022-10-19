import aiohttp_jinja2
import jinja2
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient


async def setup_db():
	db = AsyncIOMotorClient().demoserver
	first_post = await db.posts.find_one({})
	if not first_post:
		await db.posts.insert_one({'content': "Welcome to DemoServer!\n\nThis is a demonstration of using the Python libraries AIOHTTP and Motor together in a single project."})
	return db


routes = web.RouteTableDef()


@routes.get("/")
async def index_page(request: web.Request) -> web.Response:
	db = request.app["db"]
	posts = []
#	async for post in db.posts.find({}):
#		posts.append(post['content'])
#		print(post)
	
	return aiohttp_jinja2.render_template("index.html", request, context={'posts': posts})

@routes.get("/help")
async def help_page(request: web.Request) -> web.Response:
	posts = []
	return aiohttp_jinja2.render_template("help.html", request, context={'posts': posts})
	
@routes.get("/login")
async def login_page(request: web.Request) -> web.Response:
	posts = []
	return aiohttp_jinja2.render_template("login.html", request, context={'posts': posts})

@routes.get("/recallData")
async def recallData_page(request: web.Request) -> web.Response:
	posts = []
	return aiohttp_jinja2.render_template("recallData.html", request, context={'posts': posts})


@routes.post("/post")
async def make_post(request: web.Request) -> web.Response:
	db = request.app["db"]
	form_data = await request.post()
	print(form_data)
	print(type(form_data))
	post_content = form_data['content']

	print(post_content)
	
	await db.posts.insert_one({'content': post_content})
	raise web.HTTPFound('/')


async def create_app():
	global routes
	app_db = await setup_db()
	
	app = web.Application()
	aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./templates'))
	
	app["db"] = app_db
	app.add_routes(routes)
	return app


web.run_app(create_app())
